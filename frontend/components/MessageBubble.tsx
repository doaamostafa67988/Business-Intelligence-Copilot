'use client'

import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  ChevronDown, ChevronUp, Code2, Download,
  TrendingUp, Lightbulb, Target, Database, Clock
} from 'lucide-react'
import type { Message, ChatResponse, Insight, Recommendation, ChartData } from '@/types/api'
import { ChartPanel } from './ChartPanel'
import { api } from '@/lib/api'

interface Props {
  message: Message
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user'

  if (isUser) {
    return (
      <div className="flex justify-end animate-slide-up">
        <div className="max-w-2xl">
          <div className="bg-indigo-600/80 text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed">
            {message.content}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-start gap-3 animate-slide-up">
      {/* Avatar */}
      <div className="w-8 h-8 rounded-full bg-indigo-500/20 border border-indigo-500/30
        flex items-center justify-center shrink-0 mt-0.5">
        <svg className="w-4 h-4 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      </div>

      <div className="flex-1 min-w-0 space-y-3">
        {/* Main message */}
        {message.content && (
          <div className="glass-card rounded-2xl rounded-tl-sm px-4 py-3">
            <div className="prose prose-sm max-w-none text-slate-300 text-sm leading-relaxed">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content || ' '}
              </ReactMarkdown>
            </div>
          </div>
        )}

        {/* Rich content panels */}
        {message.response && <RichContent response={message.response} />}
      </div>
    </div>
  )
}

function RichContent({ response }: { response: ChatResponse }) {
  return (
    <div className="space-y-3">
      {/* KPI Cards */}
      {Object.keys(response.kpis).length > 0 && (
        <KPIGrid kpis={response.kpis} />
      )}

      {/* Charts */}
      {response.charts.length > 0 && (
        <div className="space-y-3">
          {response.charts.map((chart: ChartData, i: number) => (
            <ChartPanel key={i} chart={chart} />
          ))}
        </div>
      )}

      {/* Insights */}
      {response.insights.length > 0 && (
        <InsightsPanel insights={response.insights} />
      )}

      {/* Recommendations */}
      {response.recommendations.length > 0 && (
        <RecommendationsPanel recommendations={response.recommendations} />
      )}

      {/* HITL approval */}
      {response.awaiting_approval && (
        <ApprovalPanel response={response} />
      )}

      {/* Report download */}
      {response.has_report && response.report_filename && (
        <ReportDownload filename={response.report_filename} />
      )}

      {/* Metadata footer */}
      <MetaFooter response={response} />
    </div>
  )
}

function KPIGrid({ kpis }: { kpis: Record<string, number | string> }) {
  const entries = Object.entries(kpis).slice(0, 6)

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
      {entries.map(([key, value]) => (
        <div key={key} className="glass-card rounded-xl p-3 text-center">
          <p className="text-xs text-slate-500 mb-1">
            {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
          </p>
          <p className="text-lg font-semibold text-white">
            {typeof value === 'number' ? value.toLocaleString() : value}
          </p>
        </div>
      ))}
    </div>
  )
}

function InsightsPanel({ insights }: { insights: Insight[] }) {
  const iconMap: Record<Insight['severity'], string> = { info: '💡', warning: '⚠️', critical: '🔴' }
  const borderMap: Record<Insight['severity'], string> = {
    info: 'border-indigo-500/30 bg-indigo-500/5',
    warning: 'border-amber-500/30 bg-amber-500/5',
    critical: 'border-red-500/30 bg-red-500/5',
  }

  return (
    <div className="glass-card rounded-xl overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-slate-800/50">
        <Lightbulb className="w-4 h-4 text-indigo-400" />
        <span className="text-sm font-medium text-slate-300">Key Insights</span>
        <span className="ml-auto text-xs text-slate-500">{insights.length}</span>
      </div>
      <div className="p-3 space-y-2">
        {insights.map((ins: Insight, i: number) => (
          <div key={i} className={`rounded-lg border px-3 py-2 text-sm ${borderMap[ins.severity]}`}>
            <span className="mr-2">{iconMap[ins.severity]}</span>
            <span className="text-slate-300">{ins.text}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function RecommendationsPanel({ recommendations }: { recommendations: Recommendation[] }) {
  const priorityStyle: Record<Recommendation['priority'], string> = {
    high:   'text-red-400 border-red-500/30 bg-red-500/10',
    medium: 'text-amber-400 border-amber-500/30 bg-amber-500/10',
    low:    'text-green-400 border-green-500/30 bg-green-500/10',
  }

  return (
    <div className="glass-card rounded-xl overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-slate-800/50">
        <Target className="w-4 h-4 text-cyan-400" />
        <span className="text-sm font-medium text-slate-300">Recommendations</span>
      </div>
      <div className="p-3 space-y-2">
        {recommendations.map((rec: Recommendation, i: number) => (
          <div key={i} className="rounded-lg border border-slate-800/60 bg-slate-900/40 p-3">
            <div className="flex items-start justify-between gap-2 mb-1">
              <p className="text-sm font-medium text-slate-200">{rec.action}</p>
              <span className={`text-xs px-2 py-0.5 rounded-full border font-medium shrink-0 ${priorityStyle[rec.priority]}`}>
                {rec.priority}
              </span>
            </div>
            <p className="text-xs text-slate-500">{rec.rationale}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function ApprovalPanel({ response }: { response: ChatResponse }) {
  const [loading, setLoading] = useState(false)

  const handleApprove = async (approved: boolean) => {
    setLoading(true)
    try {
      await api.approve(response.session_id, approved)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
      <p className="text-sm text-amber-400 font-medium mb-3">
        ⚠️ Human approval required — SQL confidence is low
      </p>
      <div className="flex gap-2">
        <button
          onClick={() => handleApprove(true)}
          disabled={loading}
          className="px-4 py-2 rounded-lg bg-green-500/20 border border-green-500/30
            text-green-400 text-sm hover:bg-green-500/30 transition-colors"
        >
          ✓ Approve & Execute
        </button>
        <button
          onClick={() => handleApprove(false)}
          disabled={loading}
          className="px-4 py-2 rounded-lg bg-red-500/10 border border-red-500/30
            text-red-400 text-sm hover:bg-red-500/20 transition-colors"
        >
          ✗ Cancel
        </button>
      </div>
    </div>
  )
}

function ReportDownload({ filename }: { filename: string }) {
  return (
    <div className="rounded-xl border border-indigo-500/30 bg-indigo-500/5 p-4 flex items-center gap-3">
      <div className="w-10 h-10 rounded-lg bg-indigo-500/20 flex items-center justify-center">
        <svg className="w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
        </svg>
      </div>
      <div className="flex-1">
        <p className="text-sm font-medium text-white">Executive Report Ready</p>
        <p className="text-xs text-slate-500">PDF with full analysis and recommendations</p>
      </div>
      <a
        href={api.reportDownloadUrl(filename)}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-indigo-500
          hover:bg-indigo-400 text-white text-sm font-medium transition-colors"
      >
        <Download className="w-3.5 h-3.5" />
        Download
      </a>
    </div>
  )
}

function MetaFooter({ response }: { response: ChatResponse }) {
  const [showSQL, setShowSQL] = useState(false)
  const [showTrace, setShowTrace] = useState(false)

  return (
    <div className="flex flex-wrap items-center gap-3 pt-1">
      {/* Processing time */}
      <span className="flex items-center gap-1 text-xs text-slate-600">
        <Clock className="w-3 h-3" />
        {response.processing_ms}ms
      </span>

      {/* SQL toggle */}
      {response.sql_query && (
        <button
          onClick={() => setShowSQL(!showSQL)}
          className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-400 transition-colors"
        >
          <Database className="w-3 h-3" />
          {showSQL ? 'Hide SQL' : 'View SQL'}
          {response.sql_confidence !== undefined && (
            <span className="ml-1 text-slate-600">
              ({(response.sql_confidence * 100).toFixed(0)}% conf.)
            </span>
          )}
        </button>
      )}

      {/* Agent trace toggle */}
      {response.agent_trace.length > 0 && (
        <button
          onClick={() => setShowTrace(!showTrace)}
          className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-400 transition-colors"
        >
          <TrendingUp className="w-3 h-3" />
          {showTrace ? 'Hide trace' : 'Agent trace'}
        </button>
      )}

      {/* SQL panel */}
      {showSQL && response.sql_query && (
        <div className="w-full glass-card rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-2 border-b border-slate-800/50">
            <Code2 className="w-3.5 h-3.5 text-slate-500" />
            <span className="text-xs text-slate-500">Generated SQL</span>
          </div>
          <pre className="p-4 text-xs font-mono text-emerald-400 overflow-x-auto leading-relaxed">
            {response.sql_query}
          </pre>
        </div>
      )}

      {/* Agent trace */}
      {showTrace && response.agent_trace.length > 0 && (
        <div className="w-full flex flex-wrap gap-1.5 pt-1">
          {response.agent_trace.map((agent: string, i: number) => (
            <span key={i} className="agent-badge">{agent}</span>
          ))}
        </div>
      )}
    </div>
  )
}
