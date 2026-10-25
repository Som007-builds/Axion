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
import { ThemeToggle } from '@/components/axion/theme-toggle'
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
  'query': 'Ask a question; the answer is synthesized from retrieved graph evidence',
  'knowledge-graph': 'Explore papers, claims, and gaps; select a node or zoom in for labels',
  'contradictions': 'Model-scored candidate conflicts — not yet verified by a human',
  'gaps': 'Questions inferred from claim clusters and, when present, future-work text',
  'timeline': 'Model-interpreted consensus evolution from retrieved claims',
  'evolution': 'Heuristic claim-score distribution and the largest recomputations',
}

export default function AxionWorkspace() {
  const isClient = useIsClient()
  const [activeView, setActiveView] = useState<AxionView>('query')
  const [ingestionOpen, setIngestionOpen] = useState(false)
  const [commandQuery, setCommandQuery] = useState<string | null>(null)
  const [recentQueries, setRecentQueries] = useState<string[]>([])
  const [queryPanelLoading, setQueryPanelLoading] = useState(false)

  // Load recent queries from local storage. The query panel dispatches a
  // custom event after each history change so this menu does not stay stale
  // until a full reload.
  useEffect(() => {
    if (!isClient) return
    const loadRecent = () => {
      try {
        const stored = localStorage.getItem('axion-query-history')
        if (!stored) {
          setRecentQueries([])
          return
        }
        const parsed = JSON.parse(stored)
        setRecentQueries(
          Array.isArray(parsed)
            ? parsed
                .map((item: { question?: string }) => item?.question)
                .filter((q): q is string => typeof q === 'string')
                .slice(0, 10)
            : []
        )
      } catch {
        setRecentQueries([])
      }
    }
    loadRecent()
    window.addEventListener('axion:query-history', loadRecent)
    window.addEventListener('storage', loadRecent)
    return () => {
      window.removeEventListener('axion:query-history', loadRecent)
      window.removeEventListener('storage', loadRecent)
    }
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
      <div className="flex h-dvh w-full items-center justify-center">
        <div className="flex flex-col items-center gap-4 px-10 py-8">
          <Image
            src="/axion-logo.png"
            alt="AXION — Scientific Intelligence System"
            width={1672}
            height={941}
            priority
            className="h-20 w-auto object-contain"
          />
          <span className="cg-overline text-ink-muted">AXION SYSTEM</span>
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
    <div className="flex h-dvh w-full overflow-hidden">
      {/* Navigation Rail */}
      <NavRail
        activeView={activeView}
        onViewChange={setActiveView}
        onIngestionClick={() => setIngestionOpen(true)}
      />

      {/* Main Content Area */}
      <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Structural top rule, inset within the content column so it never
            crosses the navigation rail. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-3 top-2.5 z-40 h-[2px] bg-ink"
        />
        {/* Top Bar: Command Bar + View Title */}
        <header className="flex shrink-0 flex-col gap-3 border-b border-ink/25 px-4 pt-5 pb-3 sm:gap-4 sm:px-6 sm:pt-6 sm:pb-4">
          {/* Command Bar, with the theme switch pinned to the top-left corner
              of the content column instead of sitting in the title row. */}
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <div className="min-w-0 flex-1">
              <CommandBar
                onSubmit={handleCommandSubmit}
                recentQueries={recentQueries}
                isLoading={queryPanelLoading}
              />
            </div>
          </div>

          {/* View Header */}
          <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
            <div className="min-w-0">
              <h1 className="cg-display text-xl text-ink sm:text-2xl">
                {VIEW_TITLES[activeView]}
              </h1>
              <p className="mt-0.5 max-w-2xl text-xs leading-relaxed text-ink-soft sm:text-sm">
                {VIEW_DESCRIPTIONS[activeView]}
              </p>
            </div>

            <div className="flex min-w-0 flex-wrap items-center gap-3">
              {activeView === 'query' && (
                <div className="hidden sm:block">
                  <DashboardStats />
                </div>
              )}
            </div>
          </div>
        </header>

        {/* Active View Content */}
        <main className="flex-1 overflow-auto">
          <div
            key={activeView}
            className="mx-auto h-full w-full max-w-[1440px] animate-fade-up"
          >
            {activeView === 'query' && (
              <div className="mx-auto w-full max-w-[1200px] px-4 py-4 sm:px-6 sm:py-6">
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
              <div className="mx-auto w-full max-w-[1200px] px-4 py-4 sm:px-6 sm:py-6">
                <ContradictionList />
              </div>
            )}

            {activeView === 'gaps' && (
              <div className="mx-auto w-full max-w-[1200px] px-4 py-4 sm:px-6 sm:py-6">
                <GapList />
              </div>
            )}

            {activeView === 'timeline' && (
              <div className="mx-auto w-full max-w-[1200px] px-4 py-4 sm:px-6 sm:py-6">
                <TimelineView />
              </div>
            )}

            {activeView === 'evolution' && (
              <div className="mx-auto w-full max-w-[1200px] px-4 py-4 sm:px-6 sm:py-6">
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
