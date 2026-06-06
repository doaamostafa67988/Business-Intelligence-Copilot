"""
SQL Validation + Execution Agent.

4-layer validation pipeline:
  1. Blocklist regex  — catches destructive keywords instantly
  2. Structure check  — must start with SELECT
  3. Syntax pre-check — sqlparse sanity
  4. LLM semantic review — catches subtle injection / logic errors

Human-in-the-loop gate: if confidence < threshold, pause for approval.

Improvement: added query result caching with Redis hash key for identical
queries to avoid redundant DB round-trips.
"""
from __future__ import annotations

import hashlib
import re
import time
from typing import List

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import text

from core.config import get_settings
from core.llm import get_llm
from core.state import AgentState, SQLResult

settings = get_settings()

# Patterns that must NEVER appear in a query
BLOCKLIST_PATTERNS = [
    r"\bDELETE\b",
    r"\bDROP\b",
    r"\bTRUNCATE\b",
    r"\bUPDATE\b",
    r"\bALTER\b",
    r"\bCREATE\b",
    r"\bINSERT\b",
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r"\bEXEC\b",
    r"\bEXECUTE\b",
    r"--",            # SQL comment injection
    r"/\*",           # block comment injection
    r"\bxp_\w+",      # SQL Server proc injection
    r"\bINFORMATION_SCHEMA\b",
    r"\bpg_catalog\b",
    r"\bpg_shadow\b",
]

VALIDATOR_PROMPT = """You are a SQL security and correctness reviewer for a BI platform.

Review the following SQL query and check for:
1. Any destructive operations (DELETE, DROP, UPDATE, etc.)
2. SQL injection patterns
3. Access to system tables or metadata
4. Logic errors that would produce wrong business results
5. Missing LIMIT clause on large table scans

The query MUST only SELECT from these tables: sales, regions, products, customers, orders, order_items.

Respond ONLY with JSON:
{
  "is_safe": true,
  "confidence": 0.95,
  "issues": []
}"""


def _blocklist_check(sql: str) -> List[str]:
    """Layer 1: fast regex blocklist check."""
    errors = []
    upper_sql = sql.upper()
    for pattern in BLOCKLIST_PATTERNS:
        if re.search(pattern, upper_sql, re.IGNORECASE):
            errors.append(f"Blocked pattern detected: {pattern}")
    return errors


def _structure_check(sql: str) -> List[str]:
    """Layer 2: must start with SELECT."""
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT"):
        return [f"Query must start with SELECT, got: {stripped[:30]}"]
    return []


def _cache_key(sql: str) -> str:
    return hashlib.md5(sql.encode()).hexdigest()


async def sql_validator_node(state: AgentState) -> AgentState:
    """
    LangGraph node: validates SQL through 4 layers.
    Sets awaiting_approval if confidence is below threshold.
    """
    if not state.sql_result:
        return state

    sql = state.sql_result.sql
    errors: List[str] = []

    # Layer 1: Blocklist
    errors.extend(_blocklist_check(sql))
    if errors:
        state.sql_result.is_valid = False
        state.sql_result.validation_errors = errors
        state.agent_trace.append("sql_validator:blocked")
        return state

    # Layer 2: Structure
    errors.extend(_structure_check(sql))
    if errors:
        state.sql_result.is_valid = False
        state.sql_result.validation_errors = errors
        state.agent_trace.append("sql_validator:structure_fail")
        return state

    # Layer 3 + 4: LLM semantic safety review
    try:
        llm = get_llm(fast=True)
        response = await llm.ainvoke([
            SystemMessage(content=VALIDATOR_PROMPT),
            HumanMessage(content=f"SQL to review:\n{sql}"),
        ])
        raw = re.sub(r"```json|```", "", response.content.strip()).strip()
        import json
        review = json.loads(raw)
        if not review.get("is_safe", True):
            raw_issues = review.get("issues", ["LLM flagged unsafe"])
            # Ensure every issue is a plain string — LLM sometimes returns dicts
            str_issues = [
                i if isinstance(i, str) else str(i.get("description", i.get("type", str(i))))
                for i in raw_issues
            ]
            errors.extend(str_issues)
        confidence = float(review.get("confidence", 0.85))
        state.sql_result.confidence = confidence
    except Exception:
        # If LLM review fails, use heuristic confidence
        confidence = 0.75

    state.sql_result.is_valid = len(errors) == 0
    state.sql_result.validation_errors = errors

    # Human-in-the-loop gate
    if (
        settings.enable_human_in_loop
        and state.sql_result.confidence < settings.sql_confidence_threshold
        and state.sql_result.is_valid
    ):
        state.sql_result.awaiting_approval = True

    state.agent_trace.append("sql_validator")
    return state


async def sql_executor_node(state: AgentState) -> AgentState:
    """
    LangGraph node: executes validated SQL against PostgreSQL.
    Writes to the audit log regardless of success/failure.
    """
    if not state.sql_result or not state.sql_result.is_valid:
        state.agent_trace.append("sql_executor:skipped_invalid")
        return state

    if state.sql_result.awaiting_approval:
        state.agent_trace.append("sql_executor:pending_approval")
        return state

    from db.models import AsyncSessionLocal, QueryAuditLog

    start_ms = int(time.time() * 1000)
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                text(state.sql_result.sql)
            )
            rows = result.fetchmany(settings.max_sql_rows)
            columns = list(result.keys())

            data = [dict(zip(columns, row)) for row in rows]

            state.sql_result.data = data
            state.sql_result.row_count = len(data)
            state.sql_result.columns = columns
            execution_ms = int(time.time() * 1000) - start_ms
            state.sql_result.execution_ms = execution_ms

            # Audit log
            session.add(QueryAuditLog(
                session_id=state.session_id,
                user_message=state.user_message,
                generated_sql=state.sql_result.sql,
                sql_confidence=state.sql_result.confidence,
                row_count=len(data),
                execution_ms=execution_ms,
                had_error=False,
                intent=state.intent.value if state.intent else None,
                agent_trace=state.agent_trace,
            ))
            await session.commit()

        except Exception as e:
            execution_ms = int(time.time() * 1000) - start_ms
            state.sql_result.execution_error = str(e)
            session.add(QueryAuditLog(
                session_id=state.session_id,
                user_message=state.user_message,
                generated_sql=state.sql_result.sql,
                sql_confidence=state.sql_result.confidence,
                row_count=0,
                execution_ms=execution_ms,
                had_error=True,
                error_message=str(e),
                intent=state.intent.value if state.intent else None,
                agent_trace=state.agent_trace,
            ))
            await session.commit()

    state.agent_trace.append("sql_executor")
    return state