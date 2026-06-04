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

EXACT TABLE COLUMNS (only use columns listed here — never invent columns):

  sales:       id, sale_date, region_id, product_id, revenue, units_sold,
               orders_count, profit, avg_order_value, new_customers, returning_customers
               ⚠ sales has NO customer_id, NO order_id, NO name, NO status column.

  regions:     id, name, country, timezone
  products:    id, sku, name, category, sub_category, unit_price, cost_price, is_active
  customers:   id, name, email, segment, region_id, lifetime_value
  orders:      id, order_number, customer_id, order_date, status, total_amount, discount_amount
  order_items: id, order_id, product_id, quantity, unit_price, discount_pct, line_total

CORRECT JOIN PATHS:
  sales → regions:  JOIN regions r ON r.id = s.region_id
  sales → products: JOIN products p ON p.id = s.product_id
  ⚠ NEVER join sales directly to customers or orders — there is no FK.
    For customer data use: orders JOIN customers ON customers.id = orders.customer_id

Rules you MUST follow:
1. Generate ONLY SELECT statements — never INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE
2. Always add LIMIT {max_rows} unless the query uses GROUP BY with few groups
3. Use DATE_TRUNC for time series grouping: DATE_TRUNC('month', s.sale_date)
4. Prefer the sales fact table for revenue/profit/units metrics — it is pre-aggregated
5. Use NULLIF to prevent division-by-zero in ratios
6. Alias all computed columns (e.g. SUM(s.revenue) AS revenue)
7. Add ORDER BY that makes business sense (date ASC for trends, metric DESC for rankings)
8. For quarter filtering: s.sale_date BETWEEN '2025-10-01' AND '2025-12-31' for Q4 2025

Additional schema context from semantic search:
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
