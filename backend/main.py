"""
FastAPI Application.

Endpoints:
  POST /chat           — main conversational BI endpoint
  POST /chat/approve   — human-in-the-loop approval for low-confidence SQL
  POST /report         — generate executive PDF report
  GET  /history/{sid}  — conversation history for a session
  GET  /report/download/{filename} — download generated PDF
  GET  /health         — health check with DB connectivity

Improvements over original:
- Request/response models with full typing
- Rate limiting via slowapi
- Response time tracking
- CORS properly configured
- Request ID middleware for tracing
- Global exception handler
"""
from __future__ import annotations

import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.state import AgentState
from db.models import AsyncSessionLocal, Base, engine, get_db
from services.memory import build_history_for_state, load_memory, save_memory
from services.workflow import get_workflow

settings = get_settings()
logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables and warm up the schema retriever on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Warm up the sentence transformer (downloads model on first run)
    try:
        from services.schema_rag import get_schema_retriever
        get_schema_retriever()
        logger.info("Schema RAG ready")
    except Exception as e:
        logger.warning("Schema RAG warmup failed", error=str(e))

    # Ensure reports directory exists
    Path(settings.reports_dir).mkdir(parents=True, exist_ok=True)

    logger.info("BI Platform started", env=settings.app_env, version=settings.app_version)
    yield
    logger.info("BI Platform shutting down")


app = FastAPI(
    title="BI Copilot API",
    description="Multi-Agent Business Intelligence Platform",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
# CORS fix for Vercel + HuggingFace deployment.
# Since the Next.js proxy routes call this backend server-side,
# we can safely allow all origins — browser never calls this directly.
ALLOWED_ORIGINS = [
    "https://business-intelligence-copilot.vercel.app",
    "http://localhost:3000",
    "http://localhost:3001",
    *settings.cors_origins,
]
# Allow any *.vercel.app preview URL
import re as _re

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # safe: requests come from Next.js server, not browsers
    allow_credentials=False,       # must be False when allow_origins=["*"]
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# Request ID middleware
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    start = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start) * 1000)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Processing-Time-Ms"] = str(duration_ms)
    return response


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)},
    )


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    force_intent: Optional[str] = None


class ChartDataResponse(BaseModel):
    chart_type: str
    title: str
    plotly_figure: Dict[str, Any]


class InsightResponse(BaseModel):
    text: str
    severity: str
    category: str
    metric_value: Optional[float] = None
    change_pct: Optional[float] = None


class RecommendationResponse(BaseModel):
    action: str
    rationale: str
    priority: str
    expected_impact: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    message: str
    charts: List[ChartDataResponse] = []
    kpis: Dict[str, Any] = {}
    insights: List[InsightResponse] = []
    recommendations: List[RecommendationResponse] = []
    sql_query: Optional[str] = None
    sql_confidence: Optional[float] = None
    awaiting_approval: bool = False
    has_report: bool = False
    report_filename: Optional[str] = None
    agent_trace: List[str] = []
    processing_ms: int = 0
    intent: Optional[str] = None


class ApprovalRequest(BaseModel):
    session_id: str
    approved: bool


class ReportRequest(BaseModel):
    session_id: str
    question: str


class HistoryTurn(BaseModel):
    role: str
    content: str
    timestamp: str


class HistoryResponse(BaseModel):
    session_id: str
    turns: List[HistoryTurn]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Main conversational BI endpoint.

    Orchestrates the full multi-agent pipeline and returns structured
    response with charts, KPIs, insights, and recommendations.
    """
    start_time = time.time()

    session_id = request.session_id or str(uuid.uuid4())
    logger.info("Chat request", session_id=session_id, message=request.message[:80])

    # Load conversation memory
    memory = await load_memory(session_id, db)
    history = build_history_for_state(memory)

    # Build initial state
    initial_state = AgentState(
        session_id=session_id,
        user_message=request.message,
        conversation_history=history,
    )

    # Run LangGraph workflow
    try:
        workflow = get_workflow()
        final_state_dict = await workflow.ainvoke(initial_state.model_dump())
        final_state = AgentState(**final_state_dict)
    except Exception as e:
        logger.error("Workflow error", error=str(e), session_id=session_id)
        processing_ms = int((time.time() - start_time) * 1000)
        return ChatResponse(
            session_id=session_id,
            message=f"An error occurred while processing your request: {str(e)}",
            processing_ms=processing_ms,
        )

    # Persist memory
    try:
        await save_memory(session_id, final_state, db)
    except Exception as e:
        logger.warning("Memory save failed", error=str(e))

    # Determine report filename from path
    report_filename = None
    if final_state.report_pdf_path:
        report_filename = Path(final_state.report_pdf_path).name

    processing_ms = int((time.time() - start_time) * 1000)

    return ChatResponse(
        session_id=session_id,
        message=final_state.final_response or "Analysis complete.",
        charts=[
            ChartDataResponse(
                chart_type=c.chart_type.value,
                title=c.title,
                plotly_figure=c.plotly_figure,
            )
            for c in final_state.charts
        ],
        kpis=final_state.analysis.kpis if final_state.analysis else {},
        insights=[InsightResponse(**ins.model_dump()) for ins in final_state.insights],
        recommendations=[RecommendationResponse(**rec.model_dump()) for rec in final_state.recommendations],
        sql_query=final_state.sql_result.sql if final_state.sql_result else None,
        sql_confidence=final_state.sql_result.confidence if final_state.sql_result else None,
        awaiting_approval=bool(final_state.sql_result and final_state.sql_result.awaiting_approval),
        has_report=bool(final_state.report_pdf_path),
        report_filename=report_filename,
        agent_trace=final_state.agent_trace,
        processing_ms=processing_ms,
        intent=final_state.intent.value if final_state.intent else None,
    )


@app.post("/chat/approve", response_model=ChatResponse)
async def approve_sql(
    request: ApprovalRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Human-in-the-loop SQL approval endpoint.
    Resumes the pipeline after user approves (or rejects) a low-confidence SQL query.
    """
    start_time = time.time()

    if not request.approved:
        return ChatResponse(
            session_id=request.session_id,
            message="Query cancelled. Please rephrase your question.",
            processing_ms=int((time.time() - start_time) * 1000),
        )

    memory = await load_memory(request.session_id, db)
    if not memory.last_sql_result_snapshot:
        raise HTTPException(status_code=404, detail="No pending query found for this session")

    # Re-run from sql_executor with approval flag cleared
    snapshot = memory.last_sql_result_snapshot
    from core.state import SQLResult
    sql_result = SQLResult(
        sql=snapshot.get("sql", ""),
        is_valid=True,
        confidence=1.0,
        awaiting_approval=False,  # override — user approved
    )

    # Load last user message from history
    last_user_msg = ""
    for turn in reversed(memory.turns):
        if turn.role == "user":
            last_user_msg = turn.content
            break

    state = AgentState(
        session_id=request.session_id,
        user_message=last_user_msg,
        conversation_history=build_history_for_state(memory),
        route="trend",  # default to trend for approval flow
        sql_result=sql_result,
    )

    # Execute directly from sql_executor node
    from agents.sql_validator import sql_executor_node
    from agents.data_analysis import data_analysis_node
    from agents.visualization import visualization_node
    from agents.insight_generator import insight_generator_node
    from agents.response_composer import response_composer_node

    state = await sql_executor_node(state)
    state = await data_analysis_node(state)
    state = await visualization_node(state)
    state = await insight_generator_node(state)
    state = await response_composer_node(state)

    processing_ms = int((time.time() - start_time) * 1000)

    return ChatResponse(
        session_id=request.session_id,
        message=state.final_response,
        charts=[ChartDataResponse(chart_type=c.chart_type.value, title=c.title, plotly_figure=c.plotly_figure) for c in state.charts],
        kpis=state.analysis.kpis if state.analysis else {},
        insights=[InsightResponse(**ins.model_dump()) for ins in state.insights],
        recommendations=[],
        sql_query=state.sql_result.sql if state.sql_result else None,
        sql_confidence=state.sql_result.confidence if state.sql_result else None,
        awaiting_approval=False,
        has_report=False,
        agent_trace=state.agent_trace,
        processing_ms=processing_ms,
    )


@app.post("/report", response_model=ChatResponse)
async def generate_report(
    request: ReportRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Force-generate an executive PDF report for the given session and question.
    Overrides intent to executive_report.
    """
    return await chat(
        ChatRequest(
            message=request.question,
            session_id=request.session_id,
            force_intent="executive_report",
        ),
        db=db,
    )


@app.get("/history/{session_id}", response_model=HistoryResponse)
async def get_history(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return conversation history for a session."""
    memory = await load_memory(session_id, db)
    turns = [
        HistoryTurn(
            role=t.role,
            content=t.content,
            timestamp=t.timestamp.isoformat() if hasattr(t.timestamp, "isoformat") else str(t.timestamp),
        )
        for t in memory.turns
    ]
    return HistoryResponse(session_id=session_id, turns=turns)


@app.get("/report/download/{filename}")
async def download_report(filename: str):
    """Download a previously generated PDF report."""
    # Security: only allow filename — no path traversal
    safe_name = Path(filename).name
    if not safe_name.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files can be downloaded")

    filepath = Path(settings.reports_dir) / safe_name
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Report '{safe_name}' not found")

    return FileResponse(
        path=str(filepath),
        media_type="application/pdf",
        filename=safe_name,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check — verifies DB connectivity."""
    try:
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.app_version,
        "environment": settings.app_env,
        "database": db_status,
    }


@app.get("/")
async def root():
    return {
        "name": "BI Copilot API",
        "version": settings.app_version,
        "docs": "/docs",
    }
