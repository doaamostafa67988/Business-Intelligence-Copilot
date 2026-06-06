/**
 * API Client
 *
 * All requests go to /api/* (Next.js routes on the same origin).
 * Those routes proxy to the real backend server-side — avoiding CORS entirely.
 *
 * DO NOT call the backend URL directly from this file.
 * That would cause CORS errors in production on Vercel.
 */

import type { ChatRequest, ChatResponse, HistoryResponse } from '@/types/api'

// Always use relative URLs — calls go to Next.js proxy routes
const BASE = ''

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })

  if (!res.ok) {
    let errorMessage = `Request failed: ${res.status} ${res.statusText}`
    try {
      const errorBody = await res.json()
      errorMessage = errorBody.error || errorBody.detail || errorMessage
    } catch {
      // ignore JSON parse error
    }
    throw new Error(errorMessage)
  }

  return res.json()
}

export const api = {
  /**
   * Send a chat message.
   * Routes through: Browser → /api/chat (Next.js) → Backend
   */
  chat: (body: ChatRequest): Promise<ChatResponse> =>
    request<ChatResponse>('/api/chat', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  /**
   * Force generate an executive PDF report.
   * Routes through: Browser → /api/report (Next.js) → Backend
   */
  report: (sessionId: string, question: string): Promise<ChatResponse> =>
    request<ChatResponse>('/api/report', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, question }),
    }),

  /**
   * Fetch conversation history for a session.
   * Routes through: Browser → /api/history/[id] (Next.js) → Backend
   */
  history: (sessionId: string): Promise<HistoryResponse> =>
    request<HistoryResponse>(`/api/history/${sessionId}`),

  /**
   * Approve a low-confidence SQL query (Human-in-the-loop).
   */
  approve: (sessionId: string, approved: boolean): Promise<ChatResponse> =>
    request<ChatResponse>('/api/chat/approve', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, approved }),
    }),

  /**
   * Build a download URL for a generated PDF report.
   * Goes through the proxy to avoid CORS on the file download.
   */
  reportDownloadUrl: (filename: string): string =>
    `/api/download/${encodeURIComponent(filename)}`,
}
