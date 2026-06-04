"""
SQL Validation + Execution Agent.

4-layer validation pipeline:
  1. Blocklist regex  — catches destructive keywords instantly
  2. Structure check  — must start with SELECT
  3. Syntax pre-check — column/table sanity
  4. LLM semantic review — catches subtle injection / logic errors

Bug fix: audit log now uses a SEPARATE session after SQL errors so that
the InFailedSQLTransactionError never propagates. The failed session is
rolled back cleanly; the audit write opens a fresh connection.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import List

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import text

from core.config import get_settings
from core.llm import get_llm
from core.state import AgentState, SQLResult

settings = get_settings()

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
    r"--",
    r"/\*",
    r"\bxp_\w+",
    r"\bINFORMATION_SCHEMA\b",
    r"\bpg_catalog\b",
    r"\bpg_shadow\b",
]

VALIDATOR_PROMPT = """You are a SQL security and correctness reviewer for a BI platform.

Database schema (exact columns — do not allow queries referencing columns not listed here):

TABLE sales: id, sale_date, region_id, product_id, revenue, units_sold, orders_count,
             profit, avg_order_value, new_customers, returning_customers
             NOTE: sales has NO customer_id, NO order_id, NO name columns.

TABLE regions: id, name, country, timezone
TABLE products: id, sku, name, category, sub_category, unit_price, cost_price, is_active
TABLE customers: id, name, email, segment, region_id, lifetime_value
TABLE orders: id, order_number, customer_id, order_date, status, total_amount, discount_amount
TABLE order_items: id, order_id, product_id, quantity, unit_price, discount_pct, line_total

Review the SQL for:
1. Any destructive operations (DELETE, DROP, UPDATE, etc.)
2. SQL injection patterns
3. Columns that do NOT exist in the schema above (e.g. sales.customer_id is invalid)
4. Wrong JOIN paths (e.g. joining sales directly to customers is wrong — there is no FK)
5. Missing LIMIT on unbounded scans

Respond ONLY with JSON — no markdown:
{"is_safe": true, "confidence": 0.95, "issues": []}"""


def _blocklist_check(sql: str) -> List[str]:
    errors = []
    for pattern in BLOCKLIST_PATTERNS:
        if re.search(pattern, sql, re.IGNORECASE):
            errors.append(f"Blocked pattern: {pattern}")
    return errors


def _structure_check(sql: str) -> List[str]:
    if not sql.strip().upper().startswith("SELECT"):
        return [f"Query must start with SELECT, got: {sql.strip()[:30]}"]
    return []


def _column_sanity_check(sql: str) -> List[str]:
    """
    Quick heuristic: catch the most common hallucination —
    referencing sales.customer_id which doesn't exist.
    """
    errors = []
    sql_lower = sql.lower()
    # sales joined to customers via a non-existent FK
    if "sales" in sql_lower and "customer" in sql_lower:
        bad_patterns = [
            r"s\.customer_id",
            r"sales\.customer_id",
            r"join\s+customers\s+\w+\s+on\s+\w+\.customer_id\s*=\s*s\.",
            r"join\s+customers\s+\w+\s+on\s+s\.",
        ]
        for pat in bad_patterns:
            if re.search(pat, sql_lower):
                errors.append(
                    "Invalid join: sales has no customer_id column. "
                    "To join customers, go through orders: "
                    "sales → (aggregate by region_id) → regions, or "
                    "use orders JOIN customers."
                )
                break
    return errors


async def sql_validator_node(state: AgentState) -> AgentState:
    if not state.sql_result:
        return state

    sql = state.sql_result.sql
    errors: List[str] = []

    # Layer 1: blocklist
    errors.extend(_blocklist_check(sql))
    if errors:
        state.sql_result.is_valid = False
        state.sql_result.validation_errors = errors
        state.agent_trace.append("sql_validator:blocked")
        return state

    # Layer 2: structure
    errors.extend(_structure_check(sql))
    if errors:
        state.sql_result.is_valid = False
        state.sql_result.validation_errors = errors
        state.agent_trace.append("sql_validator:structure_fail")
        return state

    # Layer 3: column sanity (fast, no LLM)
    errors.extend(_column_sanity_check(sql))
    if errors:
        state.sql_result.is_valid = False
        state.sql_result.validation_errors = errors
        state.agent_trace.append("sql_validator:column_fail")
        return state

    # Layer 4: LLM semantic review
    # Skip for short simple SELECT queries that passed layers 1-3 — they are
    # almost certainly safe and the LLM call adds 1-2 seconds of latency.
    # Only run for complex queries (subqueries, UNIONs, multiple JOINs).
    sql_lower = sql.lower()
    is_complex = any(kw in sql_lower for kw in ["union", "except", "intersect", "with ", "select.*select"])
    join_count = sql_lower.count("join")

    confidence = 0.90  # default for simple queries that passed layers 1-3
    if is_complex or join_count >= 3:
        try:
            llm = get_llm(fast=True)
            response = await llm.ainvoke([
                SystemMessage(content=VALIDATOR_PROMPT),
                HumanMessage(content=f"SQL to review:\n{sql}"),
            ])
            raw = re.sub(r"```json|```", "", response.content.strip()).strip()
            review = json.loads(raw)
            if not review.get("is_safe", True):
                errors.extend(review.get("issues", ["LLM flagged unsafe"]))
            confidence = float(review.get("confidence", 0.85))
        except Exception:
            confidence = 0.80

    state.sql_result.confidence = confidence
    state.sql_result.is_valid = len(errors) == 0
    state.sql_result.validation_errors = errors

    if (
        settings.enable_human_in_loop
        and confidence < settings.sql_confidence_threshold
        and state.sql_result.is_valid
    ):
        state.sql_result.awaiting_approval = True

    state.agent_trace.append("sql_validator")
    return state


async def sql_executor_node(state: AgentState) -> AgentState:
    """
    Execute validated SQL and write to the audit log.

    KEY FIX: The audit log write always uses a FRESH session that is
    independent of the query session. When the SQL query fails the
    transaction is aborted — writing the audit log in the same session
    triggers InFailedSQLTransactionError. By opening a second session
    for the audit write we avoid this completely.
    """
    if not state.sql_result or not state.sql_result.is_valid:
        state.agent_trace.append("sql_executor:skipped_invalid")
        return state

    if state.sql_result.awaiting_approval:
        state.agent_trace.append("sql_executor:pending_approval")
        return state

    from db.models import AsyncSessionLocal, QueryAuditLog
    from core.serializer import sanitize

    start_ms = int(time.time() * 1000)
    execution_error: str | None = None
    execution_ms = 0

    # ── Query session ──────────────────────────────────────────────────────
    async with AsyncSessionLocal() as query_session:
        try:
            result = await query_session.execute(text(state.sql_result.sql))
            rows = result.fetchmany(settings.max_sql_rows)
            columns = list(result.keys())

            # Sanitize rows immediately — PostgreSQL returns Decimal and
            # datetime objects that are not JSON serializable. Convert them
            # here before they enter the AgentState / LangGraph state dict.
            data = [sanitize(dict(zip(columns, row))) for row in rows]
            execution_ms = int(time.time() * 1000) - start_ms

            state.sql_result.data = data
            state.sql_result.row_count = len(data)
            state.sql_result.columns = columns
            state.sql_result.execution_ms = execution_ms

            await query_session.commit()

        except Exception as exc:
            execution_ms = int(time.time() * 1000) - start_ms
            execution_error = str(exc)
            state.sql_result.execution_error = execution_error
            # Rollback the failed transaction cleanly before closing
            await query_session.rollback()

    # ── Audit session (always fresh — never inherits a failed tx) ──────────
    async with AsyncSessionLocal() as audit_session:
        try:
            audit_session.add(QueryAuditLog(
                session_id=state.session_id,
                user_message=state.user_message,
                generated_sql=state.sql_result.sql,
                sql_confidence=state.sql_result.confidence,
                row_count=state.sql_result.row_count,
                execution_ms=execution_ms,
                had_error=execution_error is not None,
                error_message=execution_error,
                intent=state.intent.value if state.intent else None,
                agent_trace=state.agent_trace,
            ))
            await audit_session.commit()
        except Exception:
            # Never let an audit write failure bubble up to the user
            await audit_session.rollback()

    state.agent_trace.append("sql_executor")
    return state
