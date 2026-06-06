// ============================================================
// API Types — mirrors backend Pydantic schemas
// ============================================================

export interface ChatRequest {
  message: string
  session_id?: string
  force_intent?: string
}

export interface ChartData {
  chart_type: string
  title: string
  plotly_figure: PlotlyFigure
}

export interface PlotlyFigure {
  data: PlotlyTrace[]
  layout: Record<string, unknown>
  frames?: unknown[]
}

export interface PlotlyTrace {
  type: string
  x?: unknown[]
  y?: unknown[]
  labels?: unknown[]
  values?: unknown[]
  name?: string
  mode?: string
  line?: Record<string, unknown>
  marker?: Record<string, unknown>
  fill?: string
  fillcolor?: string
  hole?: number
  [key: string]: unknown
}

export interface Insight {
  text: string
  severity: 'info' | 'warning' | 'critical'
  category: string
}

export interface Recommendation {
  action: string
  rationale: string
  priority: 'low' | 'medium' | 'high'
}

export interface ChatResponse {
  session_id: string
  message: string
  charts: ChartData[]
  kpis: Record<string, number | string>
  insights: Insight[]
  recommendations: Recommendation[]
  sql_query?: string
  sql_confidence?: number
  awaiting_approval: boolean
  has_report: boolean
  report_filename?: string
  agent_trace: string[]
  processing_ms: number
}

export interface HistoryTurn {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

export interface HistoryResponse {
  session_id: string
  turns: HistoryTurn[]
}

// ============================================================
// UI State Types
// ============================================================

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  response?: ChatResponse
}

export interface AppState {
  sessionId: string | null
  messages: Message[]
  isLoading: boolean
  error: string | null
}