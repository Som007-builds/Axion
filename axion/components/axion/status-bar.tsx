'use client'

import useSWR from 'swr'
import { getStats, getHealth } from '@/lib/api-client'
import type { GraphStats } from '@/types/axion'

export function StatusBar() {
  const { data, error } = useSWR<GraphStats>('stats', getStats, {
    refreshInterval: 60000,
  })
  // Real health probe (Neo4j + ChromaDB). /api/health returns 503 when a
  // datastore is down, which surfaces here as an error.
  const { data: health } = useSWR('health', getHealth, { refreshInterval: 60000 })

  const isConnected = !error && !!data && !!health
  const statusLabel = isConnected ? 'System online' : 'Degraded / offline'

  return (
    <footer className="flex h-7 shrink-0 items-center justify-between border-t border-[var(--axion-border-subtle)] bg-[var(--axion-surface-1)] px-4">
      <div className="flex items-center gap-4">
        {/* Connection Status */}
        <div className="flex items-center gap-1.5">
          <div className={`h-1.5 w-1.5 rounded-full ${isConnected ? 'bg-[#10b981]' : 'bg-[#f43f5e]'}`}>
            {isConnected && (
              <div className="h-1.5 w-1.5 rounded-full bg-[#10b981] animate-status-pulse" />
            )}
          </div>
          <span className="font-mono text-[10px] text-[#334155]">
            {statusLabel}
          </span>
        </div>

        {/* Divider */}
        <div className="h-3 w-px bg-[var(--axion-border-subtle)]" />

        {/* Stats */}
        {data && (
          <>
            <span className="font-mono text-[10px] text-[#334155]">
              {data.papers.toLocaleString()} papers
            </span>
            <span className="font-mono text-[10px] text-[#334155]">
              {data.claims.toLocaleString()} claims
            </span>
            <span className="font-mono text-[10px] text-[#334155]">
              {data.contradictions.toLocaleString()} contradictions
            </span>
          </>
        )}
      </div>

      <div className="flex items-center gap-3">
        <span className="font-mono text-[10px] text-[#1e293b]">
          AXION v2.30
        </span>
      </div>
    </footer>
  )
}
