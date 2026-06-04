"""
Recommendation Agent.

Generates prioritised business recommendations based on insights and analysis.

Improvement: adds expected_impact field and ensures recommendations are
specific and actionable (not generic platitudes).
"""
from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from core.llm import get_llm
from core.state import AgentState, Recommendation

SYSTEM_PROMPT = """You are a strategic business advisor generating recommendations for a BI platform.

Based on the insights provided, generate 3-5 specific, actionable recommendations.

Requirements:
- Each recommendation must reference a specific metric, region, or product from the data
- Include rationale grounded in the numbers
- Estimate expected impact where possible
- Prioritise by business urgency: high (immediate action needed), medium (next quarter), low (strategic)

Return ONLY valid JSON array:
[
  {
    "action": "Increase digital marketing spend in West region by 20%",
    "rationale": "West region showed 32% YoY revenue growth with highest ROI at 4.2x",
    "priority": "high",
    "expected_impact": "Estimated $500K additional revenue in Q1 2026"
  }
]"""


async def recommendation_node(state: AgentState) -> AgentState:
    """
    LangGraph node: generates prioritised business recommendations.
    """
    llm = get_llm(fast=False)

    context_parts = [f"Analysis context for: {state.user_message}"]

    if state.insights:
        insights_text = [f"- [{ins.severity.upper()}] {ins.text}" for ins in state.insights]
        context_parts.append("Key insights:\n" + "\n".join(insights_text))

    if state.analysis:
        an = state.analysis
        if an.bottom_performers:
            context_parts.append(f"Underperformers: {json.dumps(an.bottom_performers[:3])}")
        if an.outliers:
            context_parts.append(f"Anomalies: {json.dumps(an.outliers[:2])}")
        if an.growth_rates:
            context_parts.append(f"Growth: {json.dumps(an.growth_rates)}")

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content="\n".join(context_parts)),
    ]

    response = await llm.ainvoke(messages)
    raw = re.sub(r"```json|```", "", response.content.strip()).strip()

    try:
        parsed = json.loads(raw)
        recs = [Recommendation(**item) for item in parsed if isinstance(item, dict)]
    except Exception:
        recs = [
            Recommendation(
                action="Review performance data with your team",
                rationale="Detailed analysis is available in the data provided",
                priority="medium",
            )
        ]

    state.recommendations = recs
    state.agent_trace.append("recommendation")
    return state
