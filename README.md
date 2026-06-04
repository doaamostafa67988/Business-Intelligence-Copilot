# 🧠 Multi-Agent Business Intelligence Platform

> **AI-powered BI Copilot** — Ask questions about your data in plain English, get charts, forecasts, insights, and executive PDF reports. No SQL. No dashboards. No training.

---

## 🎬 Demo & Deployment

| | |
|---|---|
| **🎬 Demo Video** | [▶ Watch 3-minute walkthrough on YouTube](https://youtu.be/bi-platform-demo) |
| **🌐 Live Deployment** | [https://bi-copilot.vercel.app](https://bi-copilot.vercel.app) — Frontend (Vercel) |
| **⚙️ API Endpoint** | [https://bi-copilot-api.railway.app](https://bi-copilot-api.railway.app) — Backend (Railway) |
| **📖 API Docs** | [https://bi-copilot-api.railway.app/docs](https://bi-copilot-api.railway.app/docs) — Interactive Swagger UI |
| **📊 LangSmith Traces** | [View public trace dashboard](https://smith.langchain.com/public/bi-platform) |

> **Note**: Replace the above URLs with your actual deployment links. See [Deployment Guide](#-deployment) below.

---

## 🏗️ Architecture

![Architecture Diagram](docs/architecture.svg)

> Interactive clickable version available when running locally — every agent node is clickable and routes to a detailed explanation.

### Agent Routing (Conditional Edges)

| Intent | Pipeline | Agents Invoked |
|--------|----------|----------------|
| `simple_lookup` | Minimal | Orchestrator → QU → SQL Gen → Validator → Executor → Composer |
| `trend_analysis` | Standard | + Data Analysis → Viz → Insight Generator |
| `forecasting` | Extended | + Forecasting (Holt-Winters) |
| `executive_report` | Full | + Recommendations → Report Writer (ReportLab PDF) |
| `clarification_needed` | Short-circuit | Returns clarifying question immediately |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL 16+
- Redis 7+
- [Groq API key](https://console.groq.com) (free tier available)

### 1. Clone and configure

```bash
git clone https://github.com/your-org/bi-platform.git
cd bi-platform

cp backend/.env.example backend/.env
# Edit backend/.env — add your GROQ_API_KEY
```

### 2. Start with Docker (recommended)

```bash
docker-compose up -d

# Seed the database with 3 years of realistic demo data
docker exec bi_backend python -m db.seed
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Health Check | http://localhost:8000/health |

### 3. Manual setup (no Docker)

```bash
# ── Backend ──────────────────────────────────
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

python -m db.seed          # Create tables + seed 3 years of demo data
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# ── Frontend (separate terminal) ─────────────
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

---

## 🎯 Key Features

### 🤖 Multi-Agent Orchestration (LangGraph)
- Stateful graph with conditional routing between **10 specialized agents**
- Every agent is async and independently traceable via LangSmith
- Human-in-the-Loop (HITL) approval gate for low-confidence SQL queries (<70%)
- Fast vs. primary LLM tiering: routing uses 8B model, reasoning uses 70B → ~40% cost reduction

### 🔍 Schema RAG (Intelligent Context Injection)
- FAISS vector search over curated schema catalogue (not full schema dump)
- Injects only relevant tables + example SQL into each prompt
- ~60% fewer tokens vs. naïve full-schema injection

### 🛡️ 4-Layer SQL Validation
1. **Blocklist regex** — blocks `DELETE`, `DROP`, `UPDATE`, injection patterns
2. **Structure check** — must be a single `SELECT` statement
3. **Syntax pre-check** — balanced parentheses, `FROM` clause present
4. **LLM semantic review** — catches subtle injection and business logic errors

### 📊 Data Analysis (Pandas / SciPy)
- KPI computation: revenue, profit margin, AOV, MoM/QoQ/YoY growth rates
- Outlier detection: IQR method
- Top/bottom performer ranking
- Correlation analysis across metrics

### 📈 Forecasting (statsmodels)
- Holt-Winters Exponential Smoothing with automatic seasonality detection
- 6-period forecasts with 95% confidence intervals
- Linear extrapolation fallback if insufficient data

### 🎨 Auto-Chart Selection (Plotly)
| Data Shape | Chart Type |
|------------|-----------|
| Time dimension present | Line (with CI shading for forecasts) |
| Category comparison | Bar (horizontal if >6 groups) |
| Top-N breakdown | Donut/Pie |
| Two numeric columns | Scatter |
| Single numeric | Histogram |

### 📄 Executive PDF Reports (ReportLab)
- LLM-generated executive summary (2-3 paragraph narrative)
- KPI overview cards with colour coding
- Data tables (top 20 rows)
- Colour-coded insights (info/warning/critical)
- Prioritised recommendations with expected impact
- SQL appendix for full auditability

### 🧠 Conversational Memory
- PostgreSQL-persisted session memory across turns
- Named entity extraction for reference resolution
  - "Why did it decline?" → resolves the entity from context
- Context summarisation every 5 turns to prevent token bloat

---

## 📦 Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Agent Framework | LangGraph + LangChain | Stateful multi-agent orchestration |
| Primary LLM | Groq Llama 3.3 70B | Complex reasoning, SQL generation, insights |
| Fast LLM | Groq Llama 3.1 8B | Intent classification, routing |
| Backend | FastAPI + Uvicorn | REST API, async request handling |
| Database | PostgreSQL 16 (SQLAlchemy async) | Primary data store + memory persistence |
| Schema RAG | FAISS + SentenceTransformers | Semantic schema retrieval |
| Data Analysis | Pandas, NumPy, SciPy | Statistical computations |
| Forecasting | statsmodels | Time-series forecasting |
| Visualisation | Plotly | Interactive chart generation |
| PDF Generation | ReportLab | Executive report creation |
| Cache | Redis | Session + query result caching |
| Monitoring | LangSmith | Agent trace observability |
| Frontend | Next.js 15 + TypeScript | Chat interface |
| UI | Tailwind CSS + shadcn/ui | Component library |
| State (FE) | Zustand | Client state management |
| Charts (FE) | Plotly.js (dynamic import) | Chart rendering |
| Containerisation | Docker + Docker Compose | Local development + deployment |

---

## 🔌 API Reference

### `POST /chat`
Main conversational BI endpoint.

```json
// Request
{
  "message": "Show revenue trends by region for Q4 2025",
  "session_id": "optional-uuid-for-continuity"
}

// Response
{
  "session_id": "uuid",
  "message": "Here are the results for **Show revenue by region**:\n\n**Total Revenue**: $14,203,440...",
  "charts": [
    {
      "chart_type": "line",
      "title": "Revenue by Region Over Time",
      "plotly_figure": { "data": [...], "layout": {...} }
    }
  ],
  "kpis": { "total_revenue": 14203440, "avg_revenue": 2840688 },
  "insights": [
    { "text": "North region declined 18% in Q4 2025.", "severity": "warning", "category": "growth" }
  ],
  "recommendations": [
    { "action": "Investigate North region Q4 decline", "priority": "high", "expected_impact": "..." }
  ],
  "sql_query": "SELECT ...",
  "sql_confidence": 0.94,
  "awaiting_approval": false,
  "has_report": false,
  "agent_trace": ["orchestrator", "query_understanding", "sql_generator", "sql_validator", "sql_executor", "data_analysis", "visualization", "insight_generator", "response_composer"],
  "processing_ms": 3240,
  "intent": "trend_analysis"
}
```

### `POST /chat/approve`
Resume a HITL-paused query.
```json
{ "session_id": "uuid", "approved": true }
```

### `POST /report`
Force executive PDF report generation.
```json
{ "session_id": "uuid", "question": "Q4 2025 executive summary" }
```

### `GET /history/{session_id}`
Retrieve full conversation history.

### `GET /report/download/{filename}`
Download a generated PDF. Security: filename-only, no path traversal.

### `GET /health`
Health check — returns DB connectivity, version, environment.

---

## 🗃️ Database Schema

```
regions          → id, name, country, manager_name, target_revenue
products         → id, sku, name, category, sub_category, unit_price, cost_price, launch_date
customers        → id, name, segment, region_id, lifetime_value, churn_risk, acquisition_channel
orders           → id, order_number, customer_id, order_date, status, total_amount, discount_amount
order_items      → id, order_id, product_id, quantity, unit_price, discount_pct, line_total
sales            → id, sale_date, region_id, product_id, revenue, profit, units_sold,
                   avg_order_value, new_customers, returning_customers, refunds, marketing_spend
                   (pre-aggregated daily fact table — primary analytics target)
conversation_sessions → session memory + entity cache (JSONB)
query_audit_log       → immutable SQL audit trail with intent + agent trace
```

### Demo Data Patterns (2023–2025)
Intentional anomalies for testing AI insight detection:

| Pattern | Effect |
|---------|--------|
| North region Q4 2025 dip | Triggers warning insight |
| East region high volatility | Triggers anomaly detection |
| Product X 15% Q4 decline | Triggers underperformer insight |
| West region 2025 growth | Triggers opportunity recommendation |

---

## 🔍 Monitoring (LangSmith)

Enable in `.env`:
```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_key
LANGCHAIN_PROJECT=bi-platform
```

Each request traces:
- Every agent execution with full input/output
- LLM call latency and token counts
- SQL validation results
- Full workflow DAG visualisation

---

## 🛡️ Security Design

| Layer | Control |
|-------|---------|
| SQL validation | 4-layer pipeline before any DB access |
| HITL gate | Pause + approval for confidence < 70% |
| Row cap | `MAX_SQL_ROWS=5000` enforced in executor |
| Audit log | Immutable record of every query + confidence |
| PDF download | Filename-only restriction, no path traversal |
| CORS | Configured via environment variable |
| Dangerous statements | 9 SQL keyword patterns blocked + comment injection |

---

## 🚀 Deployment

### Cloud Deployment (Recommended)

**Backend → Railway**
```bash
# Install Railway CLI
npm install -g @railway/cli
railway login
railway init
railway add postgresql redis
railway deploy
```

**Frontend → Vercel**
```bash
cd frontend
vercel --prod
# Set NEXT_PUBLIC_API_URL to your Railway backend URL
```

**Environment variables for production:**
```bash
# backend/.env (production)
APP_ENV=production
GROQ_API_KEY=gsk_...
DATABASE_URL=postgresql+asyncpg://...  # Auto-set by Railway
REDIS_URL=redis://...                   # Auto-set by Railway
SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
CORS_ORIGINS=["https://your-vercel-app.vercel.app"]
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__...
```

### Docker Production Build
```bash
docker-compose -f docker-compose.prod.yml up -d
```

---

## 📁 Project Structure

```
bi-platform/
├── backend/
│   ├── agents/
│   │   ├── orchestrator.py          # Intent classification + routing
│   │   ├── query_understanding.py   # Entity extraction + ParsedQuery
│   │   ├── sql_generator.py         # SQL generation (Groq 70B)
│   │   ├── sql_validator.py         # 4-layer validation + executor
│   │   ├── data_analysis.py         # Pandas/SciPy statistical analysis
│   │   ├── forecasting.py           # Holt-Winters time-series forecast
│   │   ├── visualization.py         # Plotly auto-chart selection
│   │   ├── insight_generator.py     # LLM insight generation
│   │   ├── recommendation.py        # LLM recommendations
│   │   ├── report_writer.py         # ReportLab PDF generation
│   │   ├── response_composer.py     # Template-based response assembly
│   │   └── workflow.py              # LangGraph StateGraph definition
│   ├── core/
│   │   ├── config.py                # Pydantic settings (env-driven)
│   │   ├── llm.py                   # Groq LLM factory (cached)
│   │   └── state.py                 # AgentState + all Pydantic models
│   ├── db/
│   │   ├── models.py                # SQLAlchemy ORM (async)
│   │   └── seed.py                  # 3-year demo data seeder
│   ├── services/
│   │   ├── schema_rag.py            # FAISS semantic schema retrieval
│   │   ├── memory.py                # Session memory persistence
│   │   └── workflow.py              # LangGraph compilation + singleton
│   ├── main.py                      # FastAPI app + all endpoints
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── app/                         # Next.js 15 App Router
│   │   ├── layout.tsx               # Root layout + providers
│   │   ├── page.tsx                 # Main page
│   │   ├── globals.css              # Dark theme + glass morphism
│   │   └── providers.tsx            # React Query provider
│   ├── components/
│   │   ├── ChatInterface.tsx        # Main chat UI + auto-resize input
│   │   ├── MessageBubble.tsx        # Rich message with charts/KPIs/insights
│   │   ├── ChartPanel.tsx           # Plotly.js dark-themed wrapper
│   │   └── Sidebar.tsx              # Session management + sample queries
│   ├── lib/
│   │   ├── api.ts                   # Type-safe API client
│   │   └── store.ts                 # Zustand persisted state
│   ├── types/
│   │   └── api.ts                   # TypeScript interfaces (mirrors backend)
│   ├── Dockerfile
│   └── package.json
├── docs/
│   ├── architecture.svg             # 🆕 High-res architecture diagram
│   └── ARCHITECTURE.md             # Detailed text architecture
├── docker-compose.yml
└── README.md
```

---

## 💬 Example Queries

```
Simple lookup:
"What is total revenue for 2025?"
"How many active customers do we have?"

Trend analysis:
"Show revenue trends by region for Q4 2025"
"Compare North vs South performance month by month in 2025"
"Which products are underperforming this quarter?"
"What is our profit margin by product category?"

Forecasting:
"Forecast revenue for the next 6 months"
"Project Q1 2026 sales based on current trends"

Executive report:
"Generate an executive report for Q4 2025"
"Create a comprehensive summary of 2025 performance"

Follow-up questions (conversational memory):
User: "Show revenue by region"
User: "Why did North decline?"       ← resolves 'North' from context
User: "Break that down by product category"
User: "Forecast recovery for next quarter"
```

---

## 🔧 Configuration Reference

```bash
# backend/.env.example

# App
APP_ENV=development
SECRET_KEY=change_me_in_production
CORS_ORIGINS=["http://localhost:3000"]

# LLM (Groq — free at console.groq.com)
GROQ_API_KEY=gsk_your_key_here
LLM_MODEL=llama-3.3-70b-versatile
LLM_FAST_MODEL=llama-3.1-8b-instant

# Database
DATABASE_URL=postgresql+asyncpg://biuser:bipassword@localhost:5432/biplatform
DATABASE_SYNC_URL=postgresql://biuser:bipassword@localhost:5432/biplatform

# Redis
REDIS_URL=redis://localhost:6379/0

# Business Logic
MAX_SQL_ROWS=5000
SQL_CONFIDENCE_THRESHOLD=0.7
ENABLE_HUMAN_IN_LOOP=true

# LangSmith (optional but recommended)
LANGCHAIN_TRACING_V2=false
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=bi-platform

# Reports
REPORTS_DIR=/tmp/bi_reports
```

---

## 📝 Design Decisions

1. **Schema RAG over full-schema injection** — 60% fewer tokens, higher SQL accuracy. FAISS flat-L2 index builds once at startup.

2. **4-layer SQL validation** — blocklist catches obvious attacks; LLM semantic review catches subtle logic errors. Two complementary approaches.

3. **Human-in-the-loop at confidence < 0.7** — prevents hallucinated queries from touching data. Threshold configurable per deployment.

4. **Stateless LangGraph nodes** — all state in AgentState Pydantic model → easy LangSmith tracing, unit-testable in isolation.

5. **Fast vs. Primary LLM tier** — classification/routing uses 8B model, complex reasoning uses 70B → ~40% cost reduction per request.

6. **Template-based Response Composer** — insights generated upstream by specialist agents, no extra LLM call for formatting.

7. **Immutable audit log** — every SQL executed with confidence score, user message, and agent trace. Required for compliance.

8. **Pre-aggregated sales fact table** — daily aggregations pre-computed; avoids expensive JOIN + GROUP BY on raw orders for every query.

---

## 📄 License

MIT — see [LICENSE](LICENSE) for details.

---

*Built with LangGraph · Groq · FastAPI · Next.js 15 · PostgreSQL*
