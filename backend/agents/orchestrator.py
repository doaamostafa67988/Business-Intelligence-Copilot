"""
Orchestrator Agent.

Classifies the user intent and decides which pipeline to activate.
Entry point of every LangGraph workflow execution.

Routing logic:
  simple_lookup    → SQL → Response
  trend_analysis   → SQL → Analysis → Viz → Insights → Response
  forecasting      → SQL → Analysis (with forecast) → Viz → Insights → Response
  executive_report → SQL → Analysis → Viz → Insights → Recommendations → Report
  clarification    → Return clarifying question immediately
"""
from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from core.llm import get_llm
from core.state import AgentState, QueryIntent

SYSTEM_PROMPT = """You are an intent classifier for a Business Intelligence platform.

Classify the user's question into exactly one of these intents:
- simple_lookup: single metric, no trend, no comparison (e.g. "What is total revenue?")
- trend_analysis: requires time-series, comparison, or growth analysis
- forecasting: explicitly asks for forecast, prediction, next N months
- executive_report: asks for a report, summary, PDF, or comprehensive overview
- clarification_needed: question is too vague to answer without more info

Also decide if the question needs clarification. If so, write a short clarifying question.

Respond ONLY with valid JSON matching this schema:
{
  "intent": "<one of the five intents above>",
  "needs_clarification": false,
  "clarification_question": null,
  "reasoning": "<brief explanation>"
}"""


async def orchestrator_node(state: AgentState) -> AgentState:
    """
    LangGraph node: classifies intent and sets the route.

    Design: uses the fast 8B model here because this is pure
    classification — no complex reasoning needed — saving tokens on
    every request.
    """
    llm = get_llm(fast=True)

    # Build context-aware prompt including recent conversation history
    history_context = ""
    if state.conversation_history:
        last_turns = state.conversation_history[-4:]
        history_context = "\n".join(
            f"{t['role'].upper()}: {t['content']}"
            for t in last_turns
        )
        history_context = f"\n\nRecent conversation:\n{history_context}"

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=f"User question: {state.user_message}{history_context}"
        ),
    ]

    response = await llm.ainvoke(messages)
    raw = re.sub(r"```json|```", "", response.content.strip()).strip()

    try:
        parsed = json.loads(raw)
        intent = QueryIntent(parsed.get("intent", "simple_lookup"))
        needs_clarification = parsed.get("needs_clarification", False)
        clarification_q = parsed.get("clarification_question")
    except (json.JSONDecodeError, ValueError):
        intent = QueryIntent.TREND_ANALYSIS
        needs_clarification = False
        clarification_q = None

    state.intent = intent
    state.agent_trace.append("orchestrator")

    if needs_clarification and clarification_q:
        state.route = "clarification"
        state.final_response = clarification_q
    elif intent == QueryIntent.SIMPLE_LOOKUP:
        state.route = "simple"
    elif intent == QueryIntent.FORECASTING:
        state.route = "forecast"
    elif intent == QueryIntent.EXECUTIVE_REPORT:
        state.route = "report"
    else:
        state.route = "trend"

    return state
