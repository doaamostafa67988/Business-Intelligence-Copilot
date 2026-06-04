"""
Query Understanding Agent.

Extracts structured intent from natural language questions.
Handles entity resolution from conversation memory — so "Why did North
decline?" correctly resolves "North" to the region from the previous turn.
"""
from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from core.llm import get_llm
from core.state import AgentState, ParsedQuery, QueryIntent

SYSTEM_PROMPT = """You are a query understanding engine for a Business Intelligence platform.

The database contains:
- sales: daily revenue, profit, units_sold by region and product (2023-2025)
- regions: North, South, East, West, Central
- products: Software (Licenses, Add-ons, Legacy), Services (Support, Training), Hardware (Devices)
- customers: Enterprise, SMB, Consumer segments
- orders: individual transactions with status completed/returned/cancelled

Extract structured information from the user question, resolving any references
using the conversation context provided.

Return ONLY valid JSON matching this exact schema:
{
  "metric": "revenue|profit|units_sold|orders_count|customers|avg_order_value|profit_margin|null",
  "dimensions": ["region", "product", "category", "segment", "month", "quarter"],
  "date_range": "Q4 2025|2025|last 6 months|2024|null",
  "filters": {"region": "North", "category": "Software"},
  "intent": "simple_lookup|trend_analysis|forecasting|executive_report",
  "needs_forecasting": false,
  "needs_report": false,
  "ambiguity_score": 0.0,
  "clarification_question": null
}

ambiguity_score: 0.0 (crystal clear) → 1.0 (completely vague).
Resolve pronouns and references using the provided context (e.g. "it", "that region", "the product")."""


async def query_understanding_node(state: AgentState) -> AgentState:
    """LangGraph node: produces ParsedQuery from natural language."""
    llm = get_llm(fast=False)

    # Build entity context from memory for reference resolution
    entity_ctx = ""
    if state.conversation_history:
        last_entities: dict = {}
        for turn in reversed(state.conversation_history[-6:]):
            if turn.get("entities"):
                last_entities = turn["entities"]
                break
        if last_entities:
            entity_ctx = f"\nPrevious context entities: {json.dumps(last_entities)}"

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=f"User question: {state.user_message}{entity_ctx}"
        ),
    ]

    response = await llm.ainvoke(messages)
    raw = re.sub(r"```json|```", "", response.content.strip()).strip()

    try:
        data = json.loads(raw)
        parsed = ParsedQuery(**data)
    except Exception:
        parsed = ParsedQuery(
            intent=state.intent or QueryIntent.TREND_ANALYSIS,
            ambiguity_score=0.3,
        )

    state.parsed_query = parsed
    state.agent_trace.append("query_understanding")
    return state
