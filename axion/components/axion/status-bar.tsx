'use client'

import useSWR from 'swr'
import { getStats, getHealth } from '@/lib/api-client'
import type { GraphStats } from '@/types/axion'

export function StatusBar() {
  const { data, error } = useSWR<GraphStats>('stats', getStats, {
    refreshInterval: 60000,
  })
  // Real health probe. /api/health returns 503 when a datastore is down,
  // which surfaces here as an error.
  const { data: health } = useSWR('health', getHealth, { refreshInterval: 60000 })

  const isConnected = !error && !!data && !!health

  return (
    <footer className="flex h-8 shrink-0 items-center justify-between gap-3 border-t border-ink/40 px-3 pb-2 sm:px-4">
      <div className="flex min-w-0 items-center gap-4">
        {/* Connection Status */}
        <div className="flex shrink-0 items-center gap-2">
          {/* Monochrome health: filled square online / outlined "!" offline */}
          <span
            aria-hidden="true"
            className={isConnected
              ? 'inline-block h-2 w-2 bg-ink'
              : 'inline-flex h-2.5 w-2.5 items-center justify-center border-[1.5px] border-ink'}
          >
            {!isConnected && (
              <span className="bg-ink block h-0.5 w-[2px]" />
            )}
          </span>
          <span className="cg-mono-meta text-[10px] text-ink-muted">
            {isConnected ? 'SYSTEM ONLINE' : 'SYSTEM OFFLINE'}
          </span>
        </div>

        {/* Divider */}
        <div aria-hidden="true" className="h-3 w-px bg-ink/30" />

        {/* Stats — hidden on phones where the footer cannot fit them without
            silently clipping labels. The header carries the full counts. */}
        <div className="hidden min-w-0 items-center gap-4 overflow-hidden sm:flex">
          {data && (
            <>
              <span className="cg-mono-meta whitespace-nowrap text-[10px] text-ink-muted">
                {data.papers.toLocaleString()} papers
              </span>
              <span className="cg-mono-meta whitespace-nowrap text-[10px] text-ink-muted">
                {data.claims.toLocaleString()} claims
              </span>
              <span className="cg-mono-meta whitespace-nowrap text-[10px] text-ink-muted">
                {data.contradictions.toLocaleString()} contradictions
              </span>
            </>
          )}
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-3">
        <span className="cg-mono-meta text-[10px] text-ink-muted">
          AXION v2.30
        </span>
      </div>
    </footer>
  )
}
