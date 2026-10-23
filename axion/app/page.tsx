'use client'

import { useState, useCallback, useEffect } from 'react'
import Image from 'next/image'
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
import { useIsClient } from '@/lib/use-is-client'

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
  const isClient = useIsClient()
  const [activeView, setActiveView] = useState<AxionView>('query')
  const [ingestionOpen, setIngestionOpen] = useState(false)
  const [commandQuery, setCommandQuery] = useState<string | null>(null)
  const [recentQueries, setRecentQueries] = useState<string[]>([])
  const [queryPanelLoading, setQueryPanelLoading] = useState(false)

  // Load recent queries from local storage
  useEffect(() => {
    if (!isClient) return
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
  }, [isClient])

  const handleCommandSubmit = useCallback((query: string) => {
    setActiveView('query')
    setCommandQuery(query)
  }, [])

  // Keyboard shortcuts for nav
  useEffect(() => {
    if (!isClient) return
    function handleKeyDown(e: KeyboardEvent) {
      // Don't trigger shortcuts when typing in inputs
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.target instanceof HTMLElement && e.target.isContentEditable) return

      const views: AxionView[] = ['query', 'knowledge-graph', 'contradictions', 'gaps', 'timeline', 'evolution']
      const num = parseInt(e.key)
      if (num >= 1 && num <= 6) {
        setActiveView(views[num - 1])
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isClient])

  if (!isClient) {
    return (
      <div className="flex h-screen w-screen items-center justify-center">
        <div className="flex flex-col items-center gap-4 px-10 py-8">
          <Image
            src="/axion-logo.png"
            alt="AXION — Scientific Intelligence System"
            width={1672}
            height={941}
            priority
            className="h-20 w-auto object-contain"
          />
          <span className="cg-overline text-ink/70">AXION SYSTEM</span>
          <div className="flex items-center gap-2">
            <span aria-hidden="true" className="inline-block h-2 w-2 bg-ink animate-cg-blink" />
            <span className="cg-mono-meta text-xs text-ink-soft">
              Initializing workspace kernel…
            </span>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      {/* Structural top rule inset from the page edges */}
      <div
        aria-hidden="true"
        className="pointer-events-none fixed inset-x-3 top-2.5 z-40 h-[2px] bg-ink"
      />

      {/* Navigation Rail */}
      <NavRail
        activeView={activeView}
        onViewChange={setActiveView}
        onIngestionClick={() => setIngestionOpen(true)}
      />

      {/* Main Content Area */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Top Bar: Command Bar + View Title */}
        <header className="flex shrink-0 flex-col gap-4 border-b border-ink/25 px-6 pt-6 pb-4">
          {/* Command Bar */}
          <CommandBar
            onSubmit={handleCommandSubmit}
            recentQueries={recentQueries}
            isLoading={queryPanelLoading}
          />

          {/* View Header */}
          <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
            <div className="min-w-0">
              <h1 className="cg-display text-2xl text-ink">
                {VIEW_TITLES[activeView]}
              </h1>
              <p className="mt-0.5 text-sm text-ink-soft">
                {VIEW_DESCRIPTIONS[activeView]}
              </p>
            </div>

            {/* Stats (compact, inline) */}
            {activeView === 'query' && <DashboardStats />}
          </div>
        </header>

        {/* Active View Content */}
        <main className="flex-1 overflow-auto">
          <div
            key={activeView}
            className="mx-auto h-full w-full max-w-[1440px] animate-fade-up"
          >
            {activeView === 'query' && (
              <div className="mx-auto w-full max-w-[1200px] px-6 py-6">
                <QueryPanel
                  externalQuery={commandQuery}
                  onQueryClear={() => setCommandQuery(null)}
                  onLoadingChange={setQueryPanelLoading}
                />
              </div>
            )}

            {activeView === 'knowledge-graph' && (
              <KnowledgeGraph />
            )}

            {activeView === 'contradictions' && (
              <div className="mx-auto w-full max-w-[1200px] px-6 py-6">
                <ContradictionList />
              </div>
            )}

            {activeView === 'gaps' && (
              <div className="mx-auto w-full max-w-[1200px] px-6 py-6">
                <GapList />
              </div>
            )}

            {activeView === 'timeline' && (
              <div className="mx-auto w-full max-w-[1200px] px-6 py-6">
                <TimelineView />
              </div>
            )}

            {activeView === 'evolution' && (
              <div className="mx-auto w-full max-w-[1200px] px-6 py-6">
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
