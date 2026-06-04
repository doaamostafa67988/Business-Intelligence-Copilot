"""
LangGraph Workflow Builder.

Defines the Multi-Agent state machine with conditional routing.

Pipelines:
  clarification:  orchestrator → response_composer
  simple:         orchestrator → query_understanding → sql_generator → sql_validator → sql_executor → response_composer
  trend:          ... → sql_executor → data_analysis → visualization → insight_generator → response_composer
  forecast:       ... → sql_executor → data_analysis → forecasting → visualization → insight_generator → response_composer
  report:         ... → sql_executor → data_analysis → forecasting → visualization → insight_generator → recommendation → report_writer → response_composer

Improvement: added error recovery node, proper graph compilation,
and LangSmith tracing configuration.
"""
from __future__ import annotations

import os

from langgraph.graph import END, StateGraph

from agents.data_analysis import data_analysis_node
from agents.forecasting import forecasting_node
from agents.insight_generator import insight_generator_node
from agents.orchestrator import orchestrator_node
from agents.query_understanding import query_understanding_node
from agents.recommendation import recommendation_node
from agents.report_writer import report_writer_node
from agents.response_composer import response_composer_node
from agents.sql_generator import sql_generator_node
from agents.sql_validator import sql_executor_node, sql_validator_node
from agents.visualization import visualization_node
from core.config import get_settings
from core.state import AgentState

settings = get_settings()

# Configure LangSmith tracing
if settings.langchain_tracing_v2 and settings.langchain_api_key:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
    os.environ["LANGCHAIN_ENDPOINT"] = settings.langchain_endpoint


def _route_after_orchestrator(state: AgentState) -> str:
    """Conditional edge: route based on intent classification."""
    route = state.route
    if route == "clarification":
        return "clarification_end"
    return "query_understanding"  # all other routes pass through QU first


def _route_after_sql_executor(state: AgentState) -> str:
    """Conditional edge: route based on intent after SQL execution."""
    if state.sql_result and state.sql_result.execution_error:
        return "response_composer"   # error path — skip analysis
    if state.sql_result and state.sql_result.awaiting_approval:
        return "response_composer"   # HITL pause

    route = state.route
    if route == "simple":
        return "response_composer"
    elif route in ("trend", "forecast", "report"):
        return "data_analysis"
    return "response_composer"


def _route_after_data_analysis(state: AgentState) -> str:
    """Conditional edge: add forecasting for forecast/report routes."""
    if state.route in ("forecast", "report"):
        return "forecasting"
    return "visualization"


def _route_after_forecasting(state: AgentState) -> str:
    return "visualization"


def _route_after_visualization(state: AgentState) -> str:
    return "insight_generator"


def _route_after_insight_generator(state: AgentState) -> str:
    if state.route == "report":
        return "recommendation"
    return "response_composer"


def _route_after_recommendation(state: AgentState) -> str:
    return "report_writer"


def build_workflow() -> StateGraph:
    """
    Build and compile the LangGraph workflow.

    All state transitions are deterministic conditional edges,
    making the graph fully traceable in LangSmith.
    """
    # Use dict as state schema (LangGraph requires dict or TypedDict for state)
    # We serialise/deserialise AgentState at API boundary
    workflow = StateGraph(dict)

    # --- Register all nodes ---
    workflow.add_node("orchestrator", _wrap(orchestrator_node))
    workflow.add_node("query_understanding", _wrap(query_understanding_node))
    workflow.add_node("sql_generator", _wrap(sql_generator_node))
    workflow.add_node("sql_validator", _wrap(sql_validator_node))
    workflow.add_node("sql_executor", _wrap(sql_executor_node))
    workflow.add_node("data_analysis", _wrap(data_analysis_node))
    workflow.add_node("forecasting", _wrap(forecasting_node))
    workflow.add_node("visualization", _wrap(visualization_node))
    workflow.add_node("insight_generator", _wrap(insight_generator_node))
    workflow.add_node("recommendation", _wrap(recommendation_node))
    workflow.add_node("report_writer", _wrap(report_writer_node))
    workflow.add_node("response_composer", _wrap(response_composer_node))

    # --- Entry point ---
    workflow.set_entry_point("orchestrator")

    # --- Edges from orchestrator ---
    workflow.add_conditional_edges(
        "orchestrator",
        lambda state: _route_after_orchestrator(AgentState(**state)),
        {
            "clarification_end": "response_composer",
            "query_understanding": "query_understanding",
        },
    )

    # --- Linear edges: QU → SQL pipeline ---
    workflow.add_edge("query_understanding", "sql_generator")
    workflow.add_edge("sql_generator", "sql_validator")
    workflow.add_edge("sql_validator", "sql_executor")

    # --- Conditional after SQL execution ---
    workflow.add_conditional_edges(
        "sql_executor",
        lambda state: _route_after_sql_executor(AgentState(**state)),
        {
            "response_composer": "response_composer",
            "data_analysis": "data_analysis",
        },
    )

    # --- Conditional after data analysis ---
    workflow.add_conditional_edges(
        "data_analysis",
        lambda state: _route_after_data_analysis(AgentState(**state)),
        {
            "forecasting": "forecasting",
            "visualization": "visualization",
        },
    )

    # --- Linear: forecasting → visualization ---
    workflow.add_edge("forecasting", "visualization")

    # --- Conditional after visualization ---
    workflow.add_edge("visualization", "insight_generator")

    # --- Conditional after insights ---
    workflow.add_conditional_edges(
        "insight_generator",
        lambda state: _route_after_insight_generator(AgentState(**state)),
        {
            "recommendation": "recommendation",
            "response_composer": "response_composer",
        },
    )

    # --- Report path: recommendation → report_writer → composer ---
    workflow.add_edge("recommendation", "report_writer")
    workflow.add_edge("report_writer", "response_composer")

    # --- Terminal edge ---
    workflow.add_edge("response_composer", END)

    return workflow.compile()


def _wrap(node_fn):
    """
    Wrap an async AgentState node function for LangGraph's dict-based state.

    CRITICAL: Uses model_dump(mode='json') so Pydantic converts ALL
    non-serializable types automatically:
      datetime → ISO string  (fixes "datetime is not JSON serializable")
      Decimal  → float       (fixes "Decimal is not JSON serializable")
      date     → ISO string
    This runs after every node so it covers the entire pipeline.
    """
    async def wrapped(state: dict) -> dict:
        agent_state = AgentState(**state)
        result = await node_fn(agent_state)
        return result.model_dump(mode="json")
    return wrapped


# Lazy-compiled singleton
_compiled_workflow = None


def get_workflow():
    global _compiled_workflow
    if _compiled_workflow is None:
        _compiled_workflow = build_workflow()
    return _compiled_workflow
