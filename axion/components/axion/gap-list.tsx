'use client'

import { useState } from 'react'
import useSWR from 'swr'
import {
  Database,
  ExternalLink,
  FileText,
  HelpCircle,
  Layers,
  Link2,
  Search,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Overline, ErrorBanner, EmptyState } from '@/components/cg'
import { getGaps } from '@/lib/api-client'
import type { Gap, GapSource, GapsResponse } from '@/types/axion'
import { cn } from '@/lib/utils'

type SourceFilter = 'all' | GapSource

const SOURCE_ORDER: GapSource[] = [
  'cluster',
  'future_work',
  'legacy_import',
  'unknown',
]

const SOURCE_ICONS: Record<GapSource, React.ComponentType<{ className?: string }>> = {
  cluster: Layers,
  future_work: FileText,
  legacy_import: Database,
  unknown: HelpCircle,
}

function SourceMark({ source }: { source: GapSource }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'inline-block h-2 w-2 shrink-0',
        source === 'cluster' && 'bg-ink',
        source === 'future_work' && 'border border-ink/70',
        source === 'legacy_import' && 'cg-hatch border border-ink',
        source === 'unknown' && 'border border-dashed border-ink/60',
      )}
    />
  )
}

function SourceLabel({ gap }: { gap: Gap }) {
  return (
    <span
      className="inline-flex min-w-0 items-center gap-1.5"
      title={gap.source_description}
    >
      <SourceMark source={gap.source} />
      <span className="cg-overline text-ink-muted">{gap.source_label}</span>
    </span>
  )
}

function RelatedClaim({ detail }: { detail: Gap['related_claim_details'][number] }) {
  const content = (
    <>
      <p className="line-clamp-2 text-[13px] leading-relaxed text-ink">
        {detail.text || 'Claim text unavailable.'}
      </p>
      <div className="mt-1.5 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-ink-muted">
        <span>{detail.section || 'Section unrecorded'}</span>
        {detail.paper_title && (
          <span className="max-w-full truncate">{detail.paper_title}</span>
        )}
        {detail.arxiv_id && (
          <span className="cg-mono-meta inline-flex items-center gap-1 text-ink-muted">
            {detail.arxiv_id}
            <ExternalLink className="h-2.5 w-2.5" aria-hidden="true" />
          </span>
        )}
      </div>
    </>
  )

  if (detail.arxiv_id) {
    return (
      <a
        href={`https://arxiv.org/abs/${detail.arxiv_id}`}
        target="_blank"
        rel="noopener noreferrer"
        className="block min-w-0 border border-ink/15 bg-ink/[0.02] p-2.5 transition-colors duration-150 hover:border-ink/40 hover:bg-ink/5 focus-visible:outline-none"
        aria-label={`Open ${detail.arxiv_id} on arXiv: ${detail.text}`}
      >
        {content}
      </a>
    )
  }

  return (
    <div className="min-w-0 border border-ink/15 bg-ink/[0.02] p-2.5">
      {content}
    </div>
  )
}

function GapRow({ gap }: { gap: Gap }) {
  const shownClaims = gap.related_claim_details.slice(0, 5)
  const unresolved = Math.max(0, gap.related_claims.length - shownClaims.length)

  return (
    <article className="min-w-0 px-4 py-4 [&:not(:first-child)]:border-t [&:not(:first-child)]:border-ink/15 sm:px-5">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5">
        <SourceLabel gap={gap} />
        {gap.confidence != null && (
          <span
            className="cg-mono-meta text-xs text-ink tabular-nums"
            title="Self-reported by the generating model; not calibrated."
          >
            {Math.round(gap.confidence * 100)}% model score
          </span>
        )}
      </div>

      <p className="mt-2 max-w-[var(--cg-reading-max)] break-words text-[15px] leading-relaxed text-ink">
        {gap.text}
      </p>

      {gap.source === 'legacy_import' && (
        <p className="mt-2 max-w-[var(--cg-reading-max)] text-xs leading-relaxed text-ink-soft">
          {gap.source_description}
        </p>
      )}

      {gap.related_claims.length > 0 && (
        <div className="mt-3 border-t border-ink/10 pt-3">
          <div className="mb-2 flex items-center gap-1.5">
            <Link2 className="h-3 w-3 text-ink-muted" aria-hidden="true" />
            <Overline className="tracking-[0.1em] text-ink-muted">
              Related claims ({gap.related_claims.length})
            </Overline>
          </div>

          {shownClaims.length > 0 ? (
            <div className="grid min-w-0 gap-1.5 sm:grid-cols-2">
              {shownClaims.map((detail) => (
                <RelatedClaim key={detail.id} detail={detail} />
              ))}
            </div>
          ) : (
            <p className="text-xs leading-relaxed text-ink-soft">
              Linked claim records could not be resolved in the current graph.
            </p>
          )}

          {unresolved > 0 && (
            <p className="mt-2 text-[11px] text-ink-muted">
              {unresolved} linked claim{unresolved !== 1 ? 's are' : ' is'} not
              shown{shownClaims.length > 0 ? ' in the preview' : ''} or could not
              be resolved.
            </p>
          )}
        </div>
      )}
    </article>
  )
}

function GapSkeleton() {
  return (
    <div className="min-w-0 border border-ink/25 bg-paper p-4 sm:p-5">
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

  const filters: Array<{
    value: SourceFilter
    label: string
    count?: number
    icon: React.ComponentType<{ className?: string }>
  }> = [
    { value: 'all', label: 'All', count: data?.source_counts?.all, icon: Search },
    ...SOURCE_ORDER.map((source) => ({
      value: source,
      label:
        source === 'cluster'
          ? 'Cluster'
          : source === 'future_work'
            ? 'Future work'
            : source === 'legacy_import'
              ? 'Legacy'
              : 'Unknown',
      count: data?.source_counts?.[source],
      icon: SOURCE_ICONS[source],
    })),
  ]

  const activeFilter = filters.find((f) => f.value === sourceFilter)
  const futureWorkCount = data?.source_counts?.future_work

  return (
    <div className="min-w-0 space-y-6">
      <div>
        <div
          role="group"
          aria-label="Filter research gaps by extraction source"
          className="flex w-full flex-wrap items-center gap-0.5 border border-ink/40 bg-paper p-1"
        >
          {filters.map((btn) => {
            const active = sourceFilter === btn.value
            const Icon = btn.icon
            return (
              <Button
                key={btn.value}
                variant="ghost"
                size="sm"
                aria-pressed={active}
                onClick={() => setSourceFilter(btn.value)}
                className={cn(
                  'h-8 min-w-0 flex-1 basis-[calc(50%-0.25rem)] justify-start gap-1.5 px-2 text-[11px] sm:basis-auto sm:flex-none sm:justify-center sm:px-3 sm:text-xs',
                  active
                    ? 'bg-ink text-paper hover:bg-ink'
                    : 'text-ink-soft hover:bg-ink/5 hover:text-ink',
                )}
              >
                <Icon className="h-3 w-3 shrink-0" aria-hidden="true" />
                <span className="truncate">{btn.label}</span>
                {typeof btn.count === 'number' && (
                  <span
                    className={cn(
                      'cg-mono-meta text-[10px] tabular-nums',
                      active ? 'text-paper' : 'text-ink-muted',
                    )}
                  >
                    {btn.count}
                  </span>
                )}
              </Button>
            )
          })}
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-ink-muted">
          Sources describe how a gap was generated. Legacy imports do not carry a
          recoverable extraction workflow and are not treated as cluster or
          future-work gaps.
        </p>
      </div>

      {error && (
        <ErrorBanner
          title="Research gaps unavailable"
          message="Failed to load research gaps. Is the API running?"
        />
      )}

      {isLoading && (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <GapSkeleton key={i} />
          ))}
        </div>
      )}

      {data && !isLoading && (
        <>
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <p className="text-sm text-ink-soft">
              <span className="cg-mono-meta text-ink">{data.total}</span> of{' '}
              <span className="cg-mono-meta text-ink">{data.corpus_total}</span>{' '}
              gap{data.corpus_total !== 1 ? 's' : ''}
              {sourceFilter !== 'all' && (
                <>
                  {' '}with source{' '}
                  <span className="text-ink">{activeFilter?.label.toLowerCase()}</span>
                </>
              )}
            </p>
            <span className="cg-mono-meta text-[10px] text-ink-muted">
              Corpus counts are unfiltered
            </span>
          </div>

          {data.gaps.length > 0 ? (
            <div className="min-w-0 border border-ink/25 bg-paper">
              {data.gaps.map((gap) => (
                <GapRow key={gap.id} gap={gap} />
              ))}
            </div>
          ) : (
            <EmptyState
              glyph="[ ]"
              title={
                data.corpus_total === 0
                  ? 'No research gaps in the graph'
                  : `No ${activeFilter?.label.toLowerCase()} gaps`
              }
              description={
                data.corpus_total === 0
                  ? 'Run the gap-finding job after claims have been ingested. No gap records currently exist.'
                  : sourceFilter === 'future_work'
                    ? 'No gaps from future-work text are present. That extraction path is implemented but is not run by the scheduled gap job.'
                    : 'No gaps match this source. The counts above describe the full corpus, not the current filter.'
              }
              action={
                sourceFilter !== 'all' && data.corpus_total > 0 ? (
                  <Button variant="outline" size="sm" onClick={() => setSourceFilter('all')}>
                    Show all {data.corpus_total} gaps
                  </Button>
                ) : undefined
              }
            />
          )}

          {futureWorkCount === 0 && (
            <p className="border-l-2 border-ink/30 pl-3 text-[11px] leading-relaxed text-ink-muted">
              Future-work extraction is implemented but is not part of the
              scheduled gap run, so the future-work source can be empty even when
              papers contain limitations sections.
            </p>
          )}
        </>
      )}
    </div>
  )
}
