'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { ChevronDown, ChevronRight, AlertTriangle, FileText } from 'lucide-react'
import { Slider } from '@/components/ui/slider'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { ExperimentCard } from './experiment-card'
import { Overline, ErrorBanner, EmptyState, confidenceLevel } from '@/components/cg'
import { getContradictions } from '@/lib/api-client'
import type { Contradiction, ContradictionsResponse } from '@/types/axion'
import { cn } from '@/lib/utils'

function ConfidenceLevelChip({ value }: { value: number }) {
  const level = confidenceLevel(value)
  return (
    <span className="inline-flex items-center gap-2">
      <span
        aria-hidden="true"
        className={cn(
          'inline-block h-2 w-2 shrink-0',
          level === 'high' && 'bg-ink',
          level === 'medium' && 'border border-ink/70',
          level === 'low' && 'cg-hatch border border-ink'
        )}
      />
      <span className="cg-mono-meta text-xs font-medium text-ink tabular-nums">
        {Math.round(value * 100)}%
      </span>
      <span className="cg-overline text-ink/50">{level.toUpperCase()}</span>
    </span>
  )
}

function ContradictionCard({ contradiction }: { contradiction: Contradiction }) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className="transition-colors duration-150 hover:bg-ink/[0.02]">
        {/* Collapsed ledger row */}
        <CollapsibleTrigger className="flex w-full items-center gap-4 px-5 py-4 text-left focus-visible:outline-none">
          {isOpen ? (
            <ChevronDown className="h-4 w-4 shrink-0 text-ink/50" aria-hidden="true" />
          ) : (
            <ChevronRight className="h-4 w-4 shrink-0 text-ink/50" aria-hidden="true" />
          )}
          <AlertTriangle className="h-4 w-4 shrink-0 text-ink" aria-hidden="true" />
          <div className="min-w-0 flex-1 space-y-1.5">
            <div className="flex flex-wrap items-center gap-3">
              <ConfidenceLevelChip value={contradiction.confidence} />
              {contradiction.has_experiment && (
                <span className="cg-overline border border-ink/50 px-1.5 py-0.5 text-ink/70">
                  HAS EXPERIMENT
                </span>
              )}
            </div>
            <p className="line-clamp-2 text-sm leading-relaxed text-ink-soft">
              {contradiction.explanation}
            </p>
          </div>
        </CollapsibleTrigger>

        {/* Expanded dossier */}
        <CollapsibleContent>
          <div className="animate-fade-up border-t border-ink/15 px-5 py-5">
            {/* Claims side by side with centered VS */}
            <div className="relative grid items-start gap-4 md:grid-cols-[1fr_auto_1fr] md:gap-x-8">
              <div className="min-w-0 border border-ink/25 bg-paper-secondary/60 p-4">
                <div className="mb-2.5 flex items-center gap-2">
                  <span aria-hidden="true" className="inline-block h-2 w-2 bg-ink" />
                  <Overline className="text-ink/60">Position A</Overline>
                </div>
                <div className="mb-3 flex items-center gap-2 border-b border-ink/15 pb-2.5">
                  <FileText className="h-3.5 w-3.5 text-ink" aria-hidden="true" />
                  <span className="cg-mono-meta text-xs text-ink">{contradiction.paper_a}</span>
                </div>
                <p className="text-sm leading-relaxed text-ink">{contradiction.claim_a.text}</p>
                <div className="mt-2.5 flex items-center gap-3 text-xs text-ink-soft">
                  <span>{contradiction.claim_a.section}</span>
                  <span aria-hidden="true" className="h-3 w-px bg-ink/25" />
                  <span className="cg-mono-meta text-ink tabular-nums">
                    {Math.round(contradiction.claim_a.confidence * 100)}%
                  </span>
                </div>
              </div>

              {/* VS medallion — anchored center (desktop) */}
              <div className="hidden md:flex md:items-center md:justify-center md:self-start md:pt-10">
                <span className="cg-overline border border-ink/40 px-2 py-1 text-ink/70">
                  VS
                </span>
              </div>

              <div className="min-w-0 border border-ink/25 bg-paper p-4 md:bg-paper">
                <div className="mb-2.5 flex items-center gap-2">
                  <span aria-hidden="true" className="cg-hatch inline-block h-2 w-2 border border-ink" />
                  <Overline className="text-ink/60">Position B</Overline>
                </div>
                <div className="mb-3 flex items-center gap-2 border-b border-ink/15 pb-2.5">
                  <FileText className="h-3.5 w-3.5 text-ink" aria-hidden="true" />
                  <span className="cg-mono-meta text-xs text-ink">{contradiction.paper_b}</span>
                </div>
                <p className="text-sm leading-relaxed text-ink">{contradiction.claim_b.text}</p>
                <div className="mt-2.5 flex items-center gap-3 text-xs text-ink-soft">
                  <span>{contradiction.claim_b.section}</span>
                  <span aria-hidden="true" className="h-3 w-px bg-ink/25" />
                  <span className="cg-mono-meta text-ink tabular-nums">
                    {Math.round(contradiction.claim_b.confidence * 100)}%
                  </span>
                </div>
              </div>

              {/* VS for stacked layout */}
              <span
                aria-hidden="true"
                className="cg-overline w-full text-center text-ink/40 md:hidden"
              >
                · VS ·
              </span>
            </div>

            {/* Full explanation */}
            <div className="mt-5 border-l-2 border-ink/40 pl-4">
              <Overline className="text-ink/60">Contradiction Explanation</Overline>
              <p className="mt-2 text-sm leading-relaxed text-ink-soft">
                {contradiction.explanation}
              </p>
            </div>

            {/* Experiment */}
            <div className="mt-5 border-t border-ink/15 pt-4">
              <ExperimentCard
                contradictionId={contradiction.id}
                hasExperiment={contradiction.has_experiment}
              />
            </div>
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  )
}

function ContradictionSkeleton() {
  return (
    <div className="border border-ink/25 bg-paper p-5">
      <div className="flex items-center gap-3">
        <span className="cg-skeleton h-4 w-4" />
        <span className="cg-skeleton h-4 w-20" />
      </div>
      <span className="cg-skeleton mt-4 block h-3.5 w-full" />
      <span className="cg-skeleton mt-2.5 block h-3.5 w-3/4" />
    </div>
  )
}

export function ContradictionList() {
  const [minConfidence, setMinConfidence] = useState(0)

  const { data, isLoading, error } = useSWR<ContradictionsResponse>(
    ['contradictions', minConfidence],
    () => getContradictions(minConfidence / 100),
    { refreshInterval: 60000 }
  )

  return (
    <div className="space-y-6">
      {/* Filter */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border border-ink/30 bg-paper p-4">
        <div className="flex items-center gap-3">
          <Overline className="text-ink/60">Min confidence</Overline>
          <span className="cg-mono-meta text-sm text-ink tabular-nums">
            {minConfidence}%
          </span>
        </div>
        <Slider
          value={[minConfidence]}
          onValueChange={([value]) => setMinConfidence(value)}
          min={0}
          max={100}
          step={5}
          aria-label="Minimum contradiction confidence"
          className="min-w-[200px] flex-1"
        />
      </div>

      {/* Error state */}
      {error && (
        <ErrorBanner
          title="Contradictions unavailable"
          message="Failed to load contradictions. Is the API running?"
        />
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <ContradictionSkeleton key={i} />
          ))}
        </div>
      )}

      {/* Results */}
      {data && !isLoading && (
        <>
          <p className="text-sm text-ink-soft">
            <span className="cg-mono-meta text-ink">{data.total}</span>{' '}
            contradiction{data.total !== 1 ? 's' : ''} detected
          </p>
          {data.contradictions.length > 0 ? (
            <div className="divide-y divide-ink/15 border border-ink/25 bg-paper">
              {data.contradictions.map((c) => (
                <ContradictionCard key={c.id} contradiction={c} />
              ))}
            </div>
          ) : (
            <EmptyState
              glyph="△"
              title="No contradictions detected"
              description={`No contradictions found with confidence above ${minConfidence}%.`}
            />
          )}
        </>
      )}
    </div>
  )
}
