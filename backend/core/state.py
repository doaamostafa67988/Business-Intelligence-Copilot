"""
LangGraph State Definitions.

AgentState is the single shared state object that flows through
every node in the LangGraph workflow. All agents read from and
write to this object — this is the "memory" of a single request.

ConversationMemory is the persisted cross-turn memory stored in
the database / session store.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class QueryIntent(str, Enum):
    SIMPLE_LOOKUP = "simple_lookup"
    TREND_ANALYSIS = "trend_analysis"
    FORECASTING = "forecasting"
    EXECUTIVE_REPORT = "executive_report"
    CLARIFICATION_NEEDED = "clarification_needed"


class ChartType(str, Enum):
    LINE = "line"
    BAR = "bar"
    PIE = "pie"
    SCATTER = "scatter"
    HISTOGRAM = "histogram"
    HEATMAP = "heatmap"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class ParsedQuery(BaseModel):
    """Structured output from Query Understanding Agent."""
    metric: Optional[str] = None
    dimensions: List[str] = []
    date_range: Optional[str] = None
    filters: Dict[str, Any] = {}
    intent: QueryIntent = QueryIntent.SIMPLE_LOOKUP
    needs_forecasting: bool = False
    needs_report: bool = False
    ambiguity_score: float = 0.0
    clarification_question: Optional[str] = None


class SQLResult(BaseModel):
    """Result of SQL generation + validation + execution."""
    sql: str = ""
    is_valid: bool = False
    validation_errors: List[str] = []
    confidence: float = 1.0
    awaiting_approval: bool = False
    data: Optional[List[Dict[str, Any]]] = None
    row_count: int = 0
    execution_error: Optional[str] = None
    columns: List[str] = []
    execution_ms: int = 0


class AnalysisResult(BaseModel):
    """Output from Data Analysis Agent."""
    kpis: Dict[str, Any] = {}
    trends: Dict[str, Any] = {}
    growth_rates: Dict[str, Any] = {}
    outliers: List[Dict[str, Any]] = []
    correlations: Dict[str, Any] = {}
    summary_stats: Dict[str, Any] = {}
    forecast: Optional[Dict[str, Any]] = None
    top_performers: List[Dict[str, Any]] = []
    bottom_performers: List[Dict[str, Any]] = []


class ChartConfig(BaseModel):
    """Plotly-compatible chart configuration."""
    chart_type: ChartType = ChartType.BAR
    title: str = ""
    x_axis: str = ""
    y_axis: str = ""
    plotly_figure: Dict[str, Any] = {}


class Insight(BaseModel):
    """Single business insight."""
    text: str
    severity: str = "info"   # info | warning | critical
    category: str = ""       # revenue | growth | anomaly | etc.
    metric_value: Optional[float] = None
    change_pct: Optional[float] = None


class Recommendation(BaseModel):
    """Single business recommendation."""
    action: str
    rationale: str
    priority: str = "medium"   # low | medium | high
    expected_impact: Optional[str] = None


# ---------------------------------------------------------------------------
# Main LangGraph State
# ---------------------------------------------------------------------------

class AgentState(BaseModel):
    """
    Central state object shared across all LangGraph nodes.

    Design decision: using a flat Pydantic model (not TypedDict) gives
    us type safety + easy serialisation for LangSmith tracing.
    """
    # --- Input ---
    session_id: str = ""
    user_message: str = ""
    conversation_history: List[Dict[str, Any]] = []

    # --- Routing ---
    intent: Optional[QueryIntent] = None
    route: str = ""

    # --- Query Understanding ---
    parsed_query: Optional[ParsedQuery] = None

    # --- SQL ---
    schema_context: str = ""
    sql_result: Optional[SQLResult] = None

    # --- Analysis ---
    analysis: Optional[AnalysisResult] = None

    # --- Visualization ---
    charts: List[ChartConfig] = []

    # --- Insights & Recommendations ---
    insights: List[Insight] = []
    recommendations: List[Recommendation] = []

    # --- Report ---
    report_pdf_path: Optional[str] = None
    report_markdown: str = ""

    # --- Final Response ---
    final_response: str = ""
    error: Optional[str] = None

    # --- Metadata ---
    agent_trace: List[str] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    total_tokens: int = 0


# ---------------------------------------------------------------------------
# Conversation Memory (persisted across turns)
# ---------------------------------------------------------------------------

class ConversationTurn(BaseModel):
    role: str   # user | assistant
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    entities: Dict[str, Any] = {}


class ConversationMemory(BaseModel):
    """
    Persisted memory for a user session.
    Stored in PostgreSQL; loaded at the start of each turn.
    """
    session_id: str
    turns: List[ConversationTurn] = []
    context_summary: str = ""
    last_sql_result_snapshot: Optional[Dict[str, Any]] = None
    last_entities: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
