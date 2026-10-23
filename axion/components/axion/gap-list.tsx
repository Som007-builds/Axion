'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { Search, Sparkles, Link2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Overline, ErrorBanner, EmptyState } from '@/components/cg'
import { getGaps } from '@/lib/api-client'
import type { Gap, GapsResponse } from '@/types/axion'
import { cn } from '@/lib/utils'

type SourceFilter = 'all' | 'semantic' | 'llm_synthesized'

function SourceLabel({ source }: { source: Gap['source'] }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        aria-hidden="true"
        className={cn(
          'inline-block h-2 w-2',
          source === 'semantic' ? 'bg-ink' : 'border border-ink/70',
        )}
      />
      <span className="cg-overline text-ink/60">
        {source === 'semantic' ? 'SEMANTIC' : 'LLM SYNTH.'}
      </span>
    </span>
  )
}

function GapRow({ gap }: { gap: Gap }) {
  return (
    <article className="px-5 py-4 [&:not(:first-child)]:border-t [&:not(:first-child)]:border-ink/15">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <SourceLabel source={gap.source} />
        {gap.confidence != null && (
          <span className="cg-mono-meta text-xs text-ink tabular-nums">
            {Math.round(gap.confidence * 100)}% confidence
          </span>
        )}
      </div>

      <p className="mt-2 max-w-[var(--cg-reading-max)] text-[15px] leading-relaxed text-ink">
        {gap.text}
      </p>

      {gap.related_claims.length > 0 && (
        <div className="mt-3 border-t border-ink/10 pt-2.5">
          <div className="mb-2 flex items-center gap-1.5">
            <Link2 className="h-3 w-3 text-ink/50" aria-hidden="true" />
            <Overline className="tracking-[0.1em] text-ink/40">
              Related Claims ({gap.related_claims.length})
            </Overline>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {gap.related_claims.slice(0, 5).map((claimId, i) => (
              <span
                key={i}
                className="cg-mono-meta border border-ink/30 bg-ink/[0.04] px-2 py-0.5 text-[11px] text-ink"
              >
                {claimId}
              </span>
            ))}
            {gap.related_claims.length > 5 && (
              <span className="cg-mono-meta px-1 py-0.5 text-[11px] text-ink/40">
                +{gap.related_claims.length - 5} more
              </span>
            )}
          </div>
        </div>
      )}
    </article>
  )
}

function GapSkeleton() {
  return (
    <div className="border border-ink/25 bg-paper p-5">
      <div className="flex items-center gap-3">
        <span className="cg-skeleton h-3 w-20" />
        <span className="cg-skeleton h-3 w-12" />
      </div>
      <span className="cg-skeleton mt-3 block h-3.5 w-full" />
      <span className="cg-skeleton mt-2 block h-3.5 w-4/5" />
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
    { value: 'all', label: 'All', icon: <Search className="h-3 w-3" aria-hidden="true" /> },
    { value: 'semantic', label: 'Semantic', icon: <Search className="h-3 w-3" aria-hidden="true" /> },
    { value: 'llm_synthesized', label: 'LLM Synthesized', icon: <Sparkles className="h-3 w-3" aria-hidden="true" /> },
  ]

  return (
    <div className="space-y-6">
      {/* Segmented filter */}
      <div
        role="group"
        aria-label="Filter research gaps by source"
        className="inline-flex flex-wrap items-center gap-0.5 border border-ink/40 bg-paper p-1"
      >
        {filterButtons.map((btn) => {
          const active = sourceFilter === btn.value
          return (
            <Button
              key={btn.value}
              variant="ghost"
              size="sm"
              aria-pressed={active}
              onClick={() => setSourceFilter(btn.value)}
              className={cn(
                'h-7 gap-1.5 px-3 text-xs',
                active
                  ? 'bg-ink text-paper hover:bg-ink'
                  : 'text-ink-soft hover:bg-ink/5 hover:text-ink',
              )}
            >
              {btn.icon}
              <span>{btn.label}</span>
            </Button>
          )
        })}
      </div>

      {/* Error state */}
      {error && (
        <ErrorBanner
          title="Research gaps unavailable"
          message="Failed to load research gaps. Is the API running?"
        />
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
          <p className="text-sm text-ink-soft">
            <span className="cg-mono-meta text-ink">{data.total}</span>{' '}
            research gap{data.total !== 1 ? 's' : ''} identified
          </p>
          {data.gaps.length > 0 ? (
            <div className="border border-ink/25 bg-paper">
              {data.gaps.map((gap) => (
                <GapRow key={gap.id} gap={gap} />
              ))}
            </div>
          ) : (
            <EmptyState
              glyph="◇"
              title="No research gaps found"
              description="No research gaps found with the current filter."
            />
          )}
        </>
      )}
    </div>
  )
}
