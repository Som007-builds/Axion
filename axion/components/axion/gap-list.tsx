'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { Lightbulb, Sparkles, Search, Link2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { getGaps } from '@/lib/api-client'
import type { Gap, GapsResponse } from '@/types/axion'

type SourceFilter = 'all' | 'semantic' | 'llm_synthesized'

function GapCard({ gap }: { gap: Gap }) {
  return (
    <div className={`rounded-xl border axion-surface axion-card-hover p-5 space-y-3 ${
      gap.source === 'semantic' 
        ? 'border-l-2 border-l-[#3b82f6] border-[var(--axion-border-subtle)]' 
        : 'border-l-2 border-l-[#8b5cf6] border-[var(--axion-border-subtle)]'
    }`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2">
          <Lightbulb className="h-4 w-4 text-[#8b5cf6]" />
          <Badge
            variant="outline"
            className={`border-[var(--axion-border-subtle)] bg-transparent ${
              gap.source === 'semantic' 
                ? 'text-[#60a5fa]' 
                : 'text-[#a78bfa]'
            }`}
          >
            {gap.source === 'semantic' ? (
              <><Search className="mr-1 h-3 w-3" />Semantic</>
            ) : (
              <><Sparkles className="mr-1 h-3 w-3" />LLM Synthesized</>
            )}
          </Badge>
        </div>
        {gap.confidence != null && (
          <span className="text-xs text-[#475569] font-mono tabular-nums">
            {Math.round(gap.confidence * 100)}%
          </span>
        )}
      </div>
      
      <p className="text-sm text-[#f0f6ff] leading-relaxed">{gap.text}</p>
      
      {gap.related_claims.length > 0 && (
        <div className="pt-2 border-t border-[var(--axion-border-subtle)]">
          <div className="flex items-center gap-1.5 mb-2">
            <Link2 className="h-3 w-3 text-[#475569]" />
            <h5 className="text-[10px] font-medium uppercase tracking-wider text-[#475569]">
              Related Claims ({gap.related_claims.length})
            </h5>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {gap.related_claims.slice(0, 5).map((claimId, i) => (
              <span
                key={i}
                className="font-mono text-[10px] text-[#8b5cf6] rounded-md bg-[#8b5cf6]/8 border border-[#8b5cf6]/15 px-2 py-0.5"
              >
                {claimId}
              </span>
            ))}
            {gap.related_claims.length > 5 && (
              <span className="text-[10px] text-[#334155] px-1">
                +{gap.related_claims.length - 5} more
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function GapSkeleton() {
  return (
    <div className="rounded-xl border border-[var(--axion-border-subtle)] axion-surface p-5 space-y-3">
      <div className="flex items-center gap-3">
        <div className="animate-shimmer h-5 w-5 rounded" />
        <div className="animate-shimmer h-5 w-24 rounded" />
      </div>
      <div className="animate-shimmer h-4 w-full rounded" />
      <div className="animate-shimmer h-4 w-4/5 rounded" />
    </div>
  )
}

export function GapList() {
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all')

  const { data, isLoading, error } = useSWR<GapsResponse>(
    ['gaps', sourceFilter],
    () => getGaps(sourceFilter === 'all' ? undefined : sourceFilter),
    { refreshInterval: 60000 }
  )

  const filterButtons: { value: SourceFilter; label: string; icon: React.ReactNode }[] = [
    { value: 'all', label: 'All', icon: <Search className="h-3.5 w-3.5" /> },
    { value: 'semantic', label: 'Semantic', icon: <Search className="h-3.5 w-3.5" /> },
    { value: 'llm_synthesized', label: 'LLM Synthesized', icon: <Sparkles className="h-3.5 w-3.5" /> },
  ]

  return (
    <div className="space-y-6">
      {/* Filter */}
      <div className="flex items-center gap-1 rounded-xl border border-[var(--axion-border-subtle)] axion-surface p-1.5">
        {filterButtons.map((btn) => (
          <Button
            key={btn.value}
            variant="ghost"
            size="sm"
            onClick={() => setSourceFilter(btn.value)}
            className={`rounded-lg transition-all duration-150 ${
              sourceFilter === btn.value
                ? 'bg-[rgba(59,130,246,0.08)] text-[#f0f6ff]'
                : 'text-[#475569] hover:text-[#94a3b8] hover:bg-[rgba(59,130,246,0.04)]'
            }`}
          >
            {btn.icon}
            <span>{btn.label}</span>
          </Button>
        ))}
      </div>

      {/* Error state */}
      {error && (
        <div className="rounded-xl border border-[#f43f5e]/20 bg-[#f43f5e]/5 p-4">
          <p className="text-sm text-[#f43f5e]">
            Failed to load research gaps. Is the API running?
          </p>
        </div>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <GapSkeleton key={i} />
          ))}
        </div>
      )}

      {/* Results */}
      {data && !isLoading && (
        <>
          <div className="flex items-center justify-between">
            <p className="text-sm text-[#475569]">
              {data.total} research gap{data.total !== 1 ? 's' : ''} identified
            </p>
          </div>
          <div className="space-y-4 stagger-children">
            {data.gaps.map((gap) => (
              <GapCard key={gap.id} gap={gap} />
            ))}
          </div>
          {data.gaps.length === 0 && (
            <div className="rounded-xl border border-[var(--axion-border-subtle)] axion-surface p-8 text-center">
              <Lightbulb className="mx-auto h-8 w-8 text-[#334155]" />
              <p className="mt-3 text-[#94a3b8]">
                No research gaps found with the current filter
              </p>
            </div>
          )}
        </>
      )}
    </div>
  )
}
