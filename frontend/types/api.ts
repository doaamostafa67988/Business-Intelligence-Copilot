/**
 * Re-exports all types from lib/api so both import paths work:
 *   import { ChatResponse } from '@/types/api'   ← store.ts uses this
 *   import { api, ChatResponse } from '@/lib/api' ← components use this
 */
export type {
  ChatRequest,
  ChatResponse,
  ChartData,
  PlotlyFigure,
  PlotlyTrace,
  Insight,
  Recommendation,
  HistoryTurn,
  HistoryResponse,
  Message,
  AppState,
} from '@/lib/api'
