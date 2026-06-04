
╔══════════════════════════════════════════════════════════════════════════════╗
║           MULTI-AGENT BUSINESS INTELLIGENCE PLATFORM — ARCHITECTURE         ║
╚══════════════════════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND (Next.js 15)                             │
│   ┌─────────────┐  ┌──────────────────┐  ┌───────────┐  ┌───────────────┐  │
│   │  Chat UI    │  │  Plotly.js Charts │  │ KPI Cards │  │ PDF Download  │  │
│   │ (Zustand +  │  │  (dynamic import) │  │           │  │               │  │
│   │  Tailwind)  │  │                  │  │           │  │               │  │
│   └──────┬──────┘  └──────────────────┘  └───────────┘  └───────────────┘  │
└──────────┼──────────────────────────────────────────────────────────────────┘
           │  HTTP / REST (POST /chat, GET /history, GET /report/download)
           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        BACKEND (FastAPI + Uvicorn)                          │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    LANGGRAPH STATE MACHINE                           │   │
│  │                                                                      │   │
│  │  ┌──────────────┐                                                    │   │
│  │  │ Orchestrator │ ─── intent classification (fast LLM)               │   │
│  │  └──────┬───────┘                                                    │   │
│  │         │                                                            │   │
│  │    ┌────▼──────────────────────────────────────────┐                │   │
│  │    │         CONDITIONAL ROUTING                   │                │   │
│  │    │  simple → SQL → Response                      │                │   │
│  │    │  trend  → SQL → Analysis → Viz → Insights     │                │   │
│  │    │  forecast → SQL → Analysis → Forecast → Viz   │                │   │
│  │    │  report → ... → Insights → Report Writer      │                │   │
│  │    └────┬──────────────────────────────────────────┘                │   │
│  │         │                                                            │   │
│  │  ┌──────▼──────────┐   ┌──────────────────────────────────────┐     │   │
│  │  │ Query           │   │  SCHEMA RAG                          │     │   │
│  │  │ Understanding   │──▶│  (FAISS + SentenceTransformer)       │     │   │
│  │  │ Agent           │   │  Semantic schema retrieval           │     │   │
│  │  └──────┬──────────┘   └──────────────────────────────────────┘     │   │
│  │         │                                                            │   │
│  │  ┌──────▼──────────┐   ┌──────────────────────────────────────┐     │   │
│  │  │ SQL Generator   │──▶│  SQL Validator (4 layers)            │     │   │
│  │  │ Agent           │   │  1. Blocklist regex                  │     │   │
│  │  │ (Groq LLM)      │   │  2. Structure check                  │     │   │
│  │  └─────────────────┘   │  3. Syntax check                     │     │   │
│  │                        │  4. LLM semantic safety review       │     │   │
│  │                        └──────────────────┬───────────────────┘     │   │
│  │                                           │                         │   │
│  │                        ┌──────────────────▼───────────────────┐     │   │
│  │                        │  Human-in-the-Loop Gate              │     │   │
│  │                        │  (if confidence < 0.7)               │     │   │
│  │                        └──────────────────┬───────────────────┘     │   │
│  │                                           │                         │   │
│  │                        ┌──────────────────▼───────────────────┐     │   │
│  │                        │  SQL Executor → PostgreSQL           │     │   │
│  │                        │  + Audit Log write                   │     │   │
│  │                        └──────────────────┬───────────────────┘     │   │
│  │                                           │                         │   │
│  │  ┌──────────────────────────────────────────────────────────┐       │   │
│  │  │              ANALYTICS PIPELINE                          │       │   │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌────────────────┐   │       │   │
│  │  │  │ Data        │  │ Forecasting │  │ Visualization  │   │       │   │
│  │  │  │ Analysis    │─▶│ Agent       │─▶│ Agent          │   │       │   │
│  │  │  │ (Pandas /   │  │ (statsmodels│  │ (Plotly auto-  │   │       │   │
│  │  │  │  SciPy)     │  │  HW Smooth) │  │  chart select) │   │       │   │
│  │  │  └─────────────┘  └─────────────┘  └────────────────┘   │       │   │
│  │  └──────────────────────────────────────────────────────────┘       │   │
│  │                                           │                         │   │
│  │  ┌──────────────────────────────────────────────────────────┐       │   │
│  │  │              OUTPUT PIPELINE                             │       │   │
│  │  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │       │   │
│  │  │  │ Insight      │  │Recommendation│  │ Report Writer │  │       │   │
│  │  │  │ Generator    │─▶│ Agent        │─▶│ (ReportLab    │  │       │   │
│  │  │  │ (Groq LLM)   │  │ (Groq LLM)   │  │  PDF export)  │  │       │   │
│  │  │  └──────────────┘  └──────────────┘  └───────────────┘  │       │   │
│  │  └──────────────────────────────────────────────────────────┘       │   │
│  │                                           │                         │   │
│  │                        ┌──────────────────▼───────────────────┐     │   │
│  │                        │  Response Composer (no-LLM template) │     │   │
│  │                        └──────────────────────────────────────┘     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────┐    ┌────────────────────────────────────────┐  │
│  │  Memory Service          │    │  Services                             │  │
│  │  ConversationSession DB  │    │  - Schema RAG (FAISS)                 │  │
│  │  Entity resolution       │    │  - LangSmith tracing                  │  │
│  │  Context summarisation   │    │  - Audit log                          │  │
│  └─────────────────────────┘    └────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA LAYER                                        │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                    PostgreSQL 16                                       │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐  │  │
│  │  │  sales   │ │ regions  │ │ products │ │customers │ │  orders    │  │  │
│  │  │ (fact)   │ │          │ │          │ │          │ │order_items │  │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────────┘  │  │
│  │  ┌──────────────────────────┐ ┌─────────────────────────────────────┐ │  │
│  │  │  conversation_sessions   │ │      query_audit_log                │ │  │
│  │  │  (memory persistence)    │ │      (immutable compliance log)     │ │  │
│  │  └──────────────────────────┘ └─────────────────────────────────────┘ │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                    Redis 7 (session cache)                             │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘

KEY DESIGN DECISIONS:
━━━━━━━━━━━━━━━━━━━━
1. Schema RAG: FAISS vector search over schema catalogue instead of full-schema
   dump → 60% fewer tokens, higher SQL accuracy

2. 4-layer SQL validation: blocklist → structure → syntax → LLM semantic review
   Prevents destructive queries AND injection attacks

3. Human-in-the-loop: automatic pause at confidence < 0.7, user approves SQL
   Prevents hallucinated queries from touching production data

4. Stateless LangGraph nodes: all state in AgentState Pydantic model
   → Easy LangSmith tracing, testable in isolation

5. Fast vs Primary LLM tier: classification/routing uses 8B model,
   complex reasoning uses 70B → 40% cost reduction per request

6. Response Composer is template-based (no LLM): insights already generated
   upstream → saves 1 LLM call per non-report request

7. Immutable audit log: every SQL executed + confidence + user message
   → Compliance, debugging, model improvement data
