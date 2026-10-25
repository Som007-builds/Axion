'use client'

import { useState } from 'react'
import useSWR from 'swr'
import {
  ChevronDown,
  ChevronRight,
  FileText,
  ExternalLink,
  AlertTriangle,
} from 'lucide-react'
import { Slider } from '@/components/ui/slider'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { ExperimentCard } from './experiment-card'
import { Overline, ErrorBanner, EmptyState, confidenceLevel } from '@/components/cg'
import { getContradictions } from '@/lib/api-client'
import type { Claim, Contradiction, ContradictionsResponse } from '@/types/axion'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

function ScoreChip({ value }: { value: number }) {
  const level = confidenceLevel(value)
  return (
    <span
      className="inline-flex flex-wrap items-center gap-2"
      title="Uncalibrated model score for the contradiction judgment; not a probability."
    >
      <span
        aria-hidden="true"
        className={cn(
          'inline-block h-2 w-2 shrink-0',
          level === 'high' && 'bg-ink',
          level === 'medium' && 'border border-ink/70',
          level === 'low' && 'cg-hatch border border-ink',
        )}
      />
      <span className="cg-mono-meta text-xs font-medium text-ink tabular-nums">
        {Math.round(value * 100)}%
      </span>
      <span className="cg-overline text-ink-muted">Model score</span>
      <span className="cg-overline text-ink-muted">{level}</span>
    </span>
  )
}

function PaperLink({ title, arxivId }: { title: string; arxivId?: string }) {
  if (!arxivId) {
    return (
      <span className="cg-mono-meta text-xs text-ink-muted">{title}</span>
    )
  }
  return (
    <a
      href={`https://arxiv.org/abs/${arxivId}`}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex min-w-0 items-center gap-1.5 text-ink transition-colors duration-150 hover:bg-ink/5 hover:underline focus-visible:outline-none"
      aria-label={`Open ${title} on arXiv`}
    >
      <span className="cg-mono-meta truncate text-xs">{title}</span>
      <ExternalLink className="h-3 w-3 shrink-0 text-ink-muted" aria-hidden="true" />
    </a>
  )
}

function StructuredFields({ claim }: { claim: Claim }) {
  const rows = [
    ['Subject', claim.subject],
    ['Predicate', claim.predicate],
    ['Object', claim.object_val],
    ['Metric', claim.metric],
    ['Direction', claim.direction?.replace(/_/g, ' ')],
    ['Conditions', claim.conditions && claim.conditions !== '{}' ? claim.conditions : undefined],
  ].filter((row): row is [string, string] => Boolean(row[1]))

  if (rows.length === 0) return null

  return (
    <dl className="mt-3 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 border-t border-ink/10 pt-2.5 text-[11px] leading-relaxed">
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="cg-overline text-ink-muted">{label}</dt>
          <dd className="min-w-0 break-words text-ink-soft">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

function ClaimPanel({
  label,
  claim,
  paperTitle,
  hatch,
}: {
  label: string
  claim: Claim
  paperTitle: string
  hatch?: boolean
}) {
  return (
    <div className="min-w-0 border border-ink/25 bg-paper-secondary/50 p-4">
      <div className="mb-2.5 flex items-center gap-2">
        <span
          aria-hidden="true"
          className={cn(
            'inline-block h-2 w-2',
            hatch ? 'cg-hatch border border-ink' : 'bg-ink',
          )}
        />
        <Overline className="text-ink-muted">{label}</Overline>
      </div>

      <div className="mb-3 flex min-w-0 items-center gap-2 border-b border-ink/15 pb-2.5">
        <FileText className="h-3.5 w-3.5 shrink-0 text-ink" aria-hidden="true" />
        <PaperLink title={paperTitle} arxivId={claim.arxiv_id} />
      </div>

      <p className="break-words text-sm leading-relaxed text-ink">{claim.text}</p>

      <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-soft">
        <span>{claim.section || 'Section unrecorded'}</span>
        <span aria-hidden="true" className="h-3 w-px bg-ink/25" />
        <span
          className="cg-mono-meta text-ink tabular-nums"
          title="Model-reported extraction score for this claim; not calibrated."
        >
          {Math.round(claim.confidence * 100)}% extraction score
        </span>
      </div>

      {claim.evidence_span && (
        <div className="mt-3 border-l-2 border-ink/30 bg-ink/[0.03] px-3 py-2">
          <Overline className="text-ink-muted">Evidence span</Overline>
          <p className="mt-1 break-words text-xs leading-relaxed text-ink-soft">
            {claim.evidence_span}
          </p>
        </div>
      )}

      <StructuredFields claim={claim} />
    </div>
  )
}

function ContradictionCard({ contradiction }: { contradiction: Contradiction }) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className="min-w-0 transition-colors duration-150 hover:bg-ink/[0.02]">
        <CollapsibleTrigger className="flex w-full min-w-0 items-center gap-3 px-4 py-4 text-left focus-visible:outline-none sm:gap-4 sm:px-5">
          {isOpen ? (
            <ChevronDown className="h-4 w-4 shrink-0 text-ink-muted" aria-hidden="true" />
          ) : (
            <ChevronRight className="h-4 w-4 shrink-0 text-ink-muted" aria-hidden="true" />
          )}
          <AlertTriangle className="h-4 w-4 shrink-0 text-ink" aria-hidden="true" />
          <div className="min-w-0 flex-1 space-y-1.5">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <ScoreChip value={contradiction.confidence} />
              {contradiction.has_experiment && (
                <span className="cg-overline border border-ink/50 px-1.5 py-0.5 text-ink-muted">
                  Experiment draft
                </span>
              )}
            </div>
            <p className="line-clamp-2 break-words text-sm leading-relaxed text-ink-soft">
              {contradiction.explanation}
            </p>
            <p className="cg-mono-meta truncate text-[10px] text-ink-muted">
              {contradiction.paper_a} / {contradiction.paper_b}
            </p>
          </div>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <div className="animate-fade-up min-w-0 border-t border-ink/15 px-4 py-5 sm:px-5">
            <p className="mb-4 border-l-2 border-ink/40 pl-3 text-xs leading-relaxed text-ink-soft">
              Model-scored candidate conflict. Neither claim has been
              human-verified as a true contradiction; check the evidence spans
              and source papers before relying on it.
            </p>

            <div className="relative grid min-w-0 items-start gap-4 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] md:gap-x-8">
              <ClaimPanel
                label="Position A"
                claim={contradiction.claim_a}
                paperTitle={contradiction.paper_a}
              />

              <div className="hidden md:flex md:items-center md:justify-center md:self-start md:pt-10">
                <span className="cg-overline border border-ink/40 px-2 py-1 text-ink-muted">
                  VS
                </span>
              </div>

              <ClaimPanel
                label="Position B"
                claim={contradiction.claim_b}
                paperTitle={contradiction.paper_b}
                hatch
              />

              <span
                aria-hidden="true"
                className="cg-overline w-full text-center text-ink-muted md:hidden"
              >
                VS
              </span>
            </div>

            <div className="mt-5 min-w-0 border-l-2 border-ink/40 pl-4">
              <Overline className="text-ink-muted">Model explanation</Overline>
              <p className="mt-2 break-words text-sm leading-relaxed text-ink-soft">
                {contradiction.explanation}
              </p>
            </div>

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
    <div className="min-w-0 border border-ink/25 bg-paper p-4 sm:p-5">
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

  const corpusTotal = data?.corpus_total ?? data?.total ?? 0
  const shown = data?.shown ?? data?.contradictions.length ?? 0

  return (
    <div className="min-w-0 space-y-6">
      <div className="min-w-0 space-y-3">
        <div className="flex min-w-0 flex-wrap items-center gap-x-6 gap-y-3 border border-ink/30 bg-paper p-4">
          <div className="flex items-center gap-3">
            <Overline className="text-ink-muted">Minimum model score</Overline>
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
            aria-label="Minimum model score for candidate contradictions"
            className="min-w-[160px] flex-1"
          />
        </div>
        <p className="text-[11px] leading-relaxed text-ink-muted">
          Scores come from the contradiction model and are not calibrated
          probabilities. A high score is a review priority, not proof that the
          claims conflict.
        </p>
      </div>

      {error && (
        <ErrorBanner
          title="Contradictions unavailable"
          message="Failed to load candidate contradictions. Is the API running?"
        />
      )}

      {isLoading && (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <ContradictionSkeleton key={i} />
          ))}
        </div>
      )}

      {data && !isLoading && (
        <>
          <div className="space-y-1">
            <p className="text-sm text-ink-soft">
              Showing <span className="cg-mono-meta text-ink">{shown}</span> of{' '}
              <span className="cg-mono-meta text-ink">{data.total}</span>{' '}
              candidate pair{data.total !== 1 ? 's' : ''} at or above{' '}
              {minConfidence}% model score.
            </p>
            <p className="text-[11px] leading-relaxed text-ink-muted">
              The graph contains {corpusTotal.toLocaleString()} candidate pair
              {corpusTotal !== 1 ? 's' : ''}; the API returns the highest-scoring{' '}
              {shown} for this view.
            </p>
          </div>

          {data.contradictions.length > 0 ? (
            <div className="min-w-0 divide-y divide-ink/15 border border-ink/25 bg-paper">
              {data.contradictions.map((c) => (
                <ContradictionCard key={c.id} contradiction={c} />
              ))}
            </div>
          ) : (
            <EmptyState
              glyph="[ ! ]"
              title={
                corpusTotal === 0
                  ? 'No candidate contradictions in the graph'
                  : 'No pairs at this model score'
              }
              description={
                corpusTotal === 0
                  ? 'The contradiction detector has not recorded any candidate pairs. This does not by itself show that the literature agrees.'
                  : `No candidate pair reaches ${minConfidence}%. Lower the score threshold to review weaker signals.`
              }
              action={
                minConfidence > 0 ? (
                  <Button variant="outline" size="sm" onClick={() => setMinConfidence(0)}>
                    Show all scores
                  </Button>
                ) : undefined
              }
            />
          )}
        </>
      )}
    </div>
  )
}
