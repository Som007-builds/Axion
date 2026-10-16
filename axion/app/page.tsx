'use client'

import { useState, useCallback, useEffect } from 'react'
import { NavRail, type AxionView } from '@/components/axion/nav-rail'
import { CommandBar } from '@/components/axion/command-bar'
import { StatusBar } from '@/components/axion/status-bar'
import { DashboardStats } from '@/components/axion/dashboard-stats'
import { QueryPanel } from '@/components/axion/query-panel'
import { ContradictionList } from '@/components/axion/contradiction-list'
import { GapList } from '@/components/axion/gap-list'
import { TimelineView } from '@/components/axion/timeline-view'
import { GraphEvolution } from '@/components/axion/graph-evolution'
import { KnowledgeGraph } from '@/components/axion/knowledge-graph'
import { IngestionStatus } from '@/components/axion/ingestion-status'

const VIEW_TITLES: Record<AxionView, string> = {
  'query': 'Research Intelligence',
  'knowledge-graph': 'Knowledge Graph',
  'contradictions': 'Contradictions',
  'gaps': 'Research Gaps',
  'timeline': 'Timeline',
  'evolution': 'Graph Evolution',
}

const VIEW_DESCRIPTIONS: Record<AxionView, string> = {
  'query': 'Ask questions across your scientific knowledge graph',
  'knowledge-graph': 'Explore the interconnected network of papers, claims, and gaps',
  'contradictions': 'Detected conflicts between research claims',
  'gaps': 'Unexplored areas and missing connections in the literature',
  'timeline': 'Track how scientific consensus evolves over time',
  'evolution': 'Confidence distribution and claim drift analysis',
}

export default function AxionWorkspace() {
  const [mounted, setMounted] = useState(false)
  const [activeView, setActiveView] = useState<AxionView>('query')
  const [ingestionOpen, setIngestionOpen] = useState(false)
  const [commandQuery, setCommandQuery] = useState<string | null>(null)
  const [recentQueries, setRecentQueries] = useState<string[]>([])
  const [queryPanelLoading, setQueryPanelLoading] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  // Load recent queries from local storage
  useEffect(() => {
    if (!mounted) return
    try {
      const stored = localStorage.getItem('axion-query-history')
      if (stored) {
        const parsed = JSON.parse(stored)
        if (Array.isArray(parsed)) {
          setRecentQueries(
            parsed
              .map((item: { question?: string }) => item.question)
              .filter((q): q is string => typeof q === 'string')
              .slice(0, 10)
          )
        }
      }
    } catch {}
  }, [mounted])

  const handleCommandSubmit = useCallback((query: string) => {
    setActiveView('query')
    setCommandQuery(query)
  }, [])

  // Keyboard shortcuts for nav
  useEffect(() => {
    if (!mounted) return
    function handleKeyDown(e: KeyboardEvent) {
      // Don't trigger shortcuts when typing in inputs
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return

      const views: AxionView[] = ['query', 'knowledge-graph', 'contradictions', 'gaps', 'timeline', 'evolution']
      const num = parseInt(e.key)
      if (num >= 1 && num <= 6) {
        setActiveView(views[num - 1])
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [mounted])

  if (!mounted) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-black">
        <div className="flex flex-col items-center gap-4 animate-fade-up">
          {/* Premium logo loader */}
          <div className="relative flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-[#3b82f6] to-[#06b6d4] shadow-[0_0_50px_rgba(59,130,246,0.15)] after:absolute after:inset-0.5 after:rounded-[14px] after:bg-black/90 after:content-['']">
            <span className="relative z-10 font-mono text-xl font-bold tracking-tighter text-white animate-pulse">
              A
            </span>
          </div>
          <div className="flex flex-col items-center gap-1.5">
            <span className="text-[10px] text-[#475569] font-semibold tracking-[0.2em] uppercase">
              AXION SYSTEM
            </span>
            <div className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-[#3b82f6] animate-ping" />
              <span className="text-[10px] text-[#334155] font-mono">Initializing workspace kernel...</span>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-black">
      {/* Navigation Rail */}
      <NavRail
        activeView={activeView}
        onViewChange={setActiveView}
        onIngestionClick={() => setIngestionOpen(true)}
      />

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top Bar: Command Bar + View Title */}
        <header className="flex shrink-0 flex-col gap-4 border-b border-[var(--axion-border-subtle)] bg-black px-6 py-4">
          {/* Command Bar */}
          <CommandBar
            onSubmit={handleCommandSubmit}
            recentQueries={recentQueries}
            isLoading={queryPanelLoading}
          />

          {/* View Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg font-semibold text-[#f0f6ff]">
                {VIEW_TITLES[activeView]}
              </h1>
              <p className="text-xs text-[#475569]">
                {VIEW_DESCRIPTIONS[activeView]}
              </p>
            </div>

            {/* Stats (compact, inline) */}
            {activeView === 'query' && <DashboardStats />}
          </div>
        </header>

        {/* Active View Content */}
        <main className="flex-1 overflow-auto">
          <div key={activeView} className="h-full animate-fade-up">
            {activeView === 'query' && (
              <div className="mx-auto max-w-[1100px] px-6 py-6">
                <QueryPanel
                  externalQuery={commandQuery}
                  onQueryClear={() => setCommandQuery(null)}
                  onLoadingChange={setQueryPanelLoading}
                />
              </div>
            )}

            {activeView === 'knowledge-graph' && (
              <div className="h-full">
                <KnowledgeGraph />
              </div>
            )}

            {activeView === 'contradictions' && (
              <div className="mx-auto max-w-[1100px] px-6 py-6">
                <ContradictionList />
              </div>
            )}

            {activeView === 'gaps' && (
              <div className="mx-auto max-w-[1100px] px-6 py-6">
                <GapList />
              </div>
            )}

            {activeView === 'timeline' && (
              <div className="mx-auto max-w-[1100px] px-6 py-6">
                <TimelineView />
              </div>
            )}

            {activeView === 'evolution' && (
              <div className="mx-auto max-w-[1100px] px-6 py-6">
                <GraphEvolution />
              </div>
            )}
          </div>
        </main>

        {/* Status Bar */}
        <StatusBar />
      </div>

      {/* Ingestion Side Panel (Sheet) */}
      <IngestionStatus
        externalOpen={ingestionOpen}
        onExternalClose={() => setIngestionOpen(false)}
      />
    </div>
  )
}
