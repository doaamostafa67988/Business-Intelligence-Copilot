'use client'

import { BarChart3, Bot, MessageSquare, Plus, RefreshCw, Trash2, Zap } from 'lucide-react'
import { useStore } from '@/lib/store'
import { toast } from 'sonner'

const SAMPLE_QUESTIONS = [
  "Show revenue trends by region for Q4 2025",
  "Which products are underperforming this quarter?",
  "Compare North vs South region revenue for 2025",
  "Forecast next 6 months revenue",
  "What are our top 5 customers by lifetime value?",
  "Generate executive report for Q4 2025",
]

export function Sidebar() {
  const { clearSession, messages, sessionId } = useStore()

  const handleNewChat = () => {
    clearSession()
    toast.success('New conversation started')
  }

  return (
    <aside className="w-72 flex flex-col border-r border-slate-800/50 bg-slate-900/40 backdrop-blur-sm">
      {/* Header */}
      <div className="p-5 border-b border-slate-800/50">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 rounded-lg bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center">
            <BarChart3 className="w-4 h-4 text-indigo-400" />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-white">BI Copilot</h1>
            <p className="text-xs text-slate-500">Multi-Agent Platform</p>
          </div>
        </div>
      </div>

      {/* New chat */}
      <div className="p-3">
        <button
          onClick={handleNewChat}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg
            border border-indigo-500/30 bg-indigo-500/10 hover:bg-indigo-500/20
            text-indigo-300 text-sm font-medium transition-all duration-200
            hover:border-indigo-500/50 hover:glow-primary"
        >
          <Plus className="w-4 h-4" />
          New Conversation
        </button>
      </div>

      {/* Sample questions */}
      <div className="flex-1 overflow-y-auto p-3">
        <p className="text-xs text-slate-500 uppercase tracking-wider mb-3 px-1">
          Sample Questions
        </p>
        <div className="space-y-1">
          {SAMPLE_QUESTIONS.map((q, i) => (
            <SampleQuestion key={i} question={q} />
          ))}
        </div>
      </div>

      {/* Session info */}
      <div className="p-4 border-t border-slate-800/50">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          <span>Session active</span>
        </div>
        {sessionId && (
          <p className="text-xs text-slate-600 font-mono mt-1 truncate">
            {sessionId.slice(0, 16)}…
          </p>
        )}
        <div className="flex items-center gap-2 mt-2 text-xs text-slate-500">
          <MessageSquare className="w-3 h-3" />
          <span>{messages.length} messages</span>
        </div>
      </div>

      {/* Agents indicator */}
      <div className="px-4 pb-4">
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
          <p className="text-xs font-medium text-slate-400 mb-2 flex items-center gap-1">
            <Zap className="w-3 h-3 text-indigo-400" />
            Active Agents
          </p>
          <div className="flex flex-wrap gap-1">
            {['Orchestrator', 'SQL Gen', 'Analysis', 'Viz', 'Insights'].map((agent) => (
              <span key={agent} className="agent-badge text-[10px]">{agent}</span>
            ))}
          </div>
        </div>
      </div>
    </aside>
  )
}

function SampleQuestion({ question }: { question: string }) {
  const { addMessage, setLoading, sessionId, setSessionId, updateLastAssistantMessage, setError } = useStore()

  const handleClick = async () => {
    // Dynamically import to avoid SSR issues
    const { api } = await import('@/lib/api')

    addMessage({ role: 'user', content: question })
    addMessage({ role: 'assistant', content: '…' })
    setLoading(true)
    setError(null)

    try {
      const response = await api.chat({
        message: question,
        session_id: sessionId ?? undefined,
      })
      if (!sessionId) setSessionId(response.session_id)
      updateLastAssistantMessage(response)
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : 'Unknown error'
      setError(errMsg)
      toast.error('Failed to get response')
    } finally {
      setLoading(false)
    }
  }

  return (
    <button
      onClick={handleClick}
      className="w-full text-left px-3 py-2 rounded-lg text-xs text-slate-400
        hover:text-slate-200 hover:bg-slate-800/60 transition-all duration-150
        border border-transparent hover:border-slate-700/50"
    >
      {question}
    </button>
  )
}
