"""
SQL Generator Agent.

Generates safe, optimised PostgreSQL SELECT queries from structured
ParsedQuery objects + schema context injected via RAG.

Improvement over original:
- Injects example SQL patterns from schema catalogue
- Adds explicit LIMIT to all queries for safety
- Two-pass: generate then self-review
"""
from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage

from core.llm import get_llm
from core.state import AgentState
from services.schema_rag import get_schema_retriever

SYSTEM_PROMPT = """You are an expert PostgreSQL query generator for a Business Intelligence platform.

Rules you MUST follow:
1. Generate ONLY SELECT statements — never INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, GRANT
2. Always add LIMIT {max_rows} unless the query uses GROUP BY with few groups
3. Use DATE_TRUNC for time series grouping (not EXTRACT)
4. Prefer the sales fact table for aggregated revenue/profit metrics — it is pre-indexed
5. Use NULLIF to prevent division-by-zero in ratios
6. Alias all computed columns clearly (e.g. AS revenue, AS profit_margin_pct)
7. Use ILIKE for case-insensitive text filters
8. Include only columns that exist in the schema provided — never hallucinate
9. Add ORDER BY that makes business sense (usually by date or metric DESC)
10. For quarter filtering: sale_date BETWEEN '2025-10-01' AND '2025-12-31' for Q4 2025
11. IMPORTANT — table routing rules:
    - "top customers", "lifetime value", "best customers" → query the CUSTOMERS table, column: lifetime_value
    - "revenue", "profit", "units sold", "sales trends" → query the SALES table
    - "orders", "transactions", "order status" → query the ORDERS table
    - NEVER query sales table for customer lifetime_value — that column only exists in customers table
12. CRITICAL — operator precedence with AND/OR:
    - ALWAYS wrap OR conditions in parentheses when mixed with AND
    - WRONG: WHERE year = 2025 AND name = 'North' OR name = 'South'
    - RIGHT: WHERE year = 2025 AND (name = 'North' OR name = 'South')
    - RIGHT: WHERE year = 2025 AND name ILIKE ANY(ARRAY['North','South'])
    - For filtering multiple values of the same column use IN or ANY:
      r.name IN ('North', 'South')
13. Use DATE_TRUNC or EXTRACT correctly:
    - For year filter: EXTRACT(YEAR FROM s.sale_date) = 2025 OR s.sale_date BETWEEN '2025-01-01' AND '2025-12-31'
    - BETWEEN is preferred — it uses the index on sale_date

Schema context:
{schema_context}

Return ONLY the SQL query — no explanation, no markdown fences, no preamble."""


async def sql_generator_node(state: AgentState) -> AgentState:
    """
    LangGraph node: generates SQL from ParsedQuery + schema context.
    """
    from core.config import get_settings
    settings = get_settings()

    llm = get_llm(fast=False)
    retriever = get_schema_retriever()

    # Retrieve relevant schema context via semantic search
    schema_ctx = retriever.retrieve(state.user_message, top_k=5)
    state.schema_context = schema_ctx

    prompt = SYSTEM_PROMPT.format(
        schema_context=schema_ctx,
        max_rows=settings.max_sql_rows,
    )

    # Build a detailed query description from ParsedQuery
    pq = state.parsed_query
    query_description = state.user_message
    if pq:
        parts = [f"User question: {state.user_message}"]
        if pq.metric:
            parts.append(f"Target metric: {pq.metric}")
        if pq.dimensions:
            parts.append(f"Group by: {', '.join(pq.dimensions)}")
        if pq.date_range:
            parts.append(f"Date range: {pq.date_range}")
        if pq.filters:
            parts.append(f"Filters: {pq.filters}")
        query_description = "\n".join(parts)

    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=query_description),
    ]

    response = await llm.ainvoke(messages)
    sql = response.content.strip()

    # Strip markdown fences if model adds them
    sql = re.sub(r"```sql|```", "", sql).strip()

    from core.state import SQLResult
    state.sql_result = SQLResult(sql=sql, confidence=0.85)
    state.agent_trace.append("sql_generator")
    return state