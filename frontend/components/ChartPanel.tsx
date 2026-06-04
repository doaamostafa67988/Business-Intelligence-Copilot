'use client'

import { useEffect, useState } from 'react'
import type { ChartData } from '@/types/api'

interface Props {
  chart: ChartData
}

// Dynamic import for Plotly (heavy lib, SSR-unsafe)
let PlotlyModule: typeof import('react-plotly.js').default | null = null

export function ChartPanel({ chart }: Props) {
  const [Plot, setPlot] = useState<typeof import('react-plotly.js').default | null>(null)

  useEffect(() => {
    if (PlotlyModule) {
      setPlot(() => PlotlyModule)
      return
    }
    import('react-plotly.js').then((mod) => {
      PlotlyModule = mod.default
      setPlot(() => mod.default)
    })
  }, [])

  const figure = chart.plotly_figure

  // Apply our dark theme overrides on top of whatever the backend sends
  const layoutOverrides = {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { color: '#94a3b8', family: 'Inter, sans-serif', size: 12 },
    margin: { l: 50, r: 20, t: 50, b: 50 },
    xaxis: {
      gridcolor: 'rgba(148,163,184,0.1)',
      zerolinecolor: 'rgba(148,163,184,0.2)',
      ...(figure.layout?.xaxis ?? {}),
    },
    yaxis: {
      gridcolor: 'rgba(148,163,184,0.1)',
      zerolinecolor: 'rgba(148,163,184,0.2)',
      ...(figure.layout?.yaxis ?? {}),
    },
    ...figure.layout,
    title: {
      text: chart.title,
      font: { color: '#e2e8f0', size: 13, family: 'Inter, sans-serif' },
      ...(typeof figure.layout?.title === 'object' ? figure.layout.title : {}),
    },
    legend: {
      bgcolor: 'rgba(0,0,0,0)',
      font: { color: '#94a3b8' },
      ...(figure.layout?.legend ?? {}),
    },
  }

  return (
    <div className="glass-card rounded-xl overflow-hidden">
      <div className="px-4 py-2.5 border-b border-slate-800/50 flex items-center gap-2">
        <ChartIcon type={chart.chart_type} />
        <span className="text-sm text-slate-400 font-medium truncate">{chart.title}</span>
        <span className="ml-auto text-xs text-slate-600 uppercase tracking-wider">
          {chart.chart_type}
        </span>
      </div>

      <div className="p-2">
        {Plot ? (
          <Plot
            data={(figure.data as Plotly.Data[]) ?? []}
            layout={layoutOverrides as Partial<Plotly.Layout>}
            config={{
              displayModeBar: true,
              displaylogo: false,
              modeBarButtonsToRemove: ['sendDataToCloud', 'autoScale2d', 'select2d', 'lasso2d'],
              toImageButtonOptions: {
                format: 'png',
                filename: `bi_chart_${Date.now()}`,
                scale: 2,
              },
            }}
            style={{ width: '100%', height: 320 }}
            useResizeHandler
          />
        ) : (
          <div className="h-72 flex items-center justify-center">
            <div className="flex flex-col items-center gap-2 text-slate-500">
              <div className="w-6 h-6 border-2 border-indigo-500/50 border-t-indigo-500 rounded-full animate-spin" />
              <span className="text-xs">Loading chart…</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function ChartIcon({ type }: { type: string }) {
  const icons: Record<string, string> = {
    line: '📈',
    bar: '📊',
    pie: '🥧',
    scatter: '⚡',
    histogram: '📉',
    heatmap: '🗺️',
  }
  return <span className="text-base">{icons[type] ?? '📊'}</span>
}
