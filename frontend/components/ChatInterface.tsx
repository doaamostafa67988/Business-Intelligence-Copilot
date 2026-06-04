'use client'

import { useEffect, useRef, useState } from 'react'
import { Send, Loader2, AlertCircle } from 'lucide-react'
import { toast } from 'sonner'
import { useStore } from '@/lib/store'
import { MessageBubble } from './MessageBubble'
import { api } from '@/lib/api'

export function ChatInterface() {
  const {
    messages,
    isLoading,
    sessionId,
    error,
    addMessage,
    setLoading,
    setError,
    setSessionId,
    updateLastAssistantMessage,
  } = useStore()

  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 160) + 'px'
  }, [input])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const msg = input.trim()
    if (!msg || isLoading) return

    setInput('')
    addMessage({ role: 'user', content: msg })
    addMessage({ role: 'assistant', content: '' })
    setLoading(true)
    setError(null)

    try {
      const response = await api.chat({
        message: msg,
        session_id: sessionId ?? undefined,
      })
      if (!sessionId) setSessionId(response.session_id)
      updateLastAssistantMessage(response)

      if (response.has_report && response.report_filename) {
        toast.success('Executive report ready!', {
          action: {
            label: 'Download PDF',
            onClick: () => {
              window.open(api.reportDownloadUrl(response.report_filename!), '_blank')
            },
          },
        })
      }
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : 'Unknown error'
      setError(errMsg)
      updateLastAssistantMessage({
        session_id: sessionId ?? '',
        message: `Sorry, I encountered an error: ${errMsg}`,
        charts: [],
        kpis: {},
        insights: [],
        recommendations: [],
        awaiting_approval: false,
        has_report: false,
        agent_trace: [],
        processing_ms: 0,
      })
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e as unknown as React.FormEvent)
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="px-6 py-4 border-b border-slate-800/50 flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-white">Business Intelligence Copilot</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Ask questions about your data in plain English
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs text-slate-500">
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
            Groq · Llama 3.3
          </span>
          <span className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-400" />
            LangGraph
          </span>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6">
        {messages.length === 0 && <EmptyState />}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {isLoading && <ThinkingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* Error banner */}
      {error && (
        <div className="mx-4 mb-2 p-3 rounded-lg border border-red-500/30 bg-red-500/10 flex items-center gap-2 text-sm text-red-400">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Input */}
      <div className="p-4 border-t border-slate-800/50">
        <form onSubmit={handleSubmit} className="relative">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything about your data… (Shift+Enter for new line)"
            rows={1}
            disabled={isLoading}
            className="w-full resize-none rounded-xl border border-slate-700/60
              bg-slate-900/60 backdrop-blur-sm px-4 py-3 pr-14
              text-sm text-slate-100 placeholder-slate-500
              focus:outline-none focus:border-indigo-500/60 focus:ring-1 focus:ring-indigo-500/30
              disabled:opacity-50 transition-all duration-200
              font-sans leading-relaxed"
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="absolute right-3 bottom-3 w-8 h-8 rounded-lg
              bg-indigo-500 hover:bg-indigo-400 disabled:bg-slate-700
              flex items-center justify-center transition-all duration-200
              disabled:cursor-not-allowed"
          >
            {isLoading
              ? <Loader2 className="w-4 h-4 text-white animate-spin" />
              : <Send className="w-4 h-4 text-white" />
            }
          </button>
        </form>
        <p className="text-center text-xs text-slate-600 mt-2">
          Powered by LangGraph · PostgreSQL · Groq Llama 3.3 70B
        </p>
      </div>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full py-20 text-center">
      <div className="w-16 h-16 rounded-2xl bg-indigo-500/10 border border-indigo-500/20
        flex items-center justify-center mb-4">
        <svg className="w-8 h-8 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
      </div>
      <h3 className="text-lg font-semibold text-white mb-2">Ready to analyse your data</h3>
      <p className="text-sm text-slate-500 max-w-sm">
        Ask about revenue trends, product performance, regional comparisons,
        forecasts, or request an executive report.
      </p>
    </div>
  )
}

function ThinkingIndicator() {
  return (
    <div className="flex items-start gap-3 animate-fade-in">
      <div className="w-8 h-8 rounded-full bg-indigo-500/20 border border-indigo-500/30
        flex items-center justify-center shrink-0 mt-0.5">
        <svg className="w-4 h-4 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      </div>
      <div className="glass-card rounded-xl px-4 py-3 flex items-center gap-2">
        <span className="text-sm text-slate-400">Agents working</span>
        <div className="flex gap-1 ml-1">
          {[0, 1, 2].map((i) => (
            <div key={i} className="w-1.5 h-1.5 rounded-full bg-indigo-400 loading-dot"
              style={{ animationDelay: `${i * 0.16}s` }} />
          ))}
        </div>
      </div>
    </div>
  )
}
