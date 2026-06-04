"""
Insight Generator Agent.

Converts numerical analysis results into executive-level natural language insights.

Uses the primary LLM with structured JSON output, then parses into typed Insight objects.

Improvement: adds severity classification, metric values and change percentages
to each insight for richer frontend display.
"""
from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from core.llm import get_llm
from core.state import AgentState, Insight

SYSTEM_PROMPT = """You are a senior business analyst generating executive insights for a BI platform.

Given analysis data, generate 3-6 concise, actionable insights.

Each insight MUST include:
- A specific metric with its value
- Comparison to a baseline (previous period, target, or average)
- Business implication

Severity levels:
- "info": positive or neutral finding
- "warning": concerning trend requiring attention
- "critical": significant decline or risk

Categories: revenue, growth, anomaly, performance, customer, product

Return ONLY valid JSON array:
[
  {
    "text": "Revenue increased 18.2% YoY to $4.2M in Q4 2025, driven by West region (+32%).",
    "severity": "info",
    "category": "growth",
    "metric_value": 4200000,
    "change_pct": 18.2
  }
]"""


async def insight_generator_node(state: AgentState) -> AgentState:
    """
    LangGraph node: generates structured business insights.
    """
    if not state.analysis and not state.sql_result:
        state.agent_trace.append("insight_generator:no_data")
        return state

    llm = get_llm(fast=False)

    # Build rich context for the LLM
    context_parts = [f"User question: {state.user_message}"]

    if state.analysis:
        an = state.analysis
        if an.kpis:
            context_parts.append(f"KPIs: {json.dumps(an.kpis)}")
        if an.growth_rates:
            context_parts.append(f"Growth rates: {json.dumps(an.growth_rates)}")
        if an.top_performers:
            context_parts.append(f"Top performers: {json.dumps(an.top_performers[:3])}")
        if an.bottom_performers:
            context_parts.append(f"Bottom performers: {json.dumps(an.bottom_performers[:3])}")
        if an.outliers:
            context_parts.append(f"Anomalies detected: {json.dumps(an.outliers[:3])}")

    if state.sql_result and state.sql_result.data:
        sample = state.sql_result.data[:5]
        context_parts.append(f"Sample data (first 5 rows): {json.dumps(sample)}")

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content="\n".join(context_parts)),
    ]

    response = await llm.ainvoke(messages)
    raw = re.sub(r"```json|```", "", response.content.strip()).strip()

    try:
        parsed = json.loads(raw)
        insights = [Insight(**item) for item in parsed if isinstance(item, dict)]
    except Exception:
        # Fallback: generate a basic insight from KPIs
        insights = []
        if state.analysis and state.analysis.kpis:
            for key, val in list(state.analysis.kpis.items())[:3]:
                if "total" in key:
                    insights.append(Insight(
                        text=f"{key.replace('_', ' ').title()}: {val:,.2f}" if isinstance(val, float) else f"{key.replace('_', ' ').title()}: {val}",
                        severity="info",
                        category="revenue",
                    ))

    state.insights = insights
    state.agent_trace.append("insight_generator")
    return state
