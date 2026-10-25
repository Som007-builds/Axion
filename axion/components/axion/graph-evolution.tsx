'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { RefreshCw, Loader2, ExternalLink, FileText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Overline, ErrorBanner } from '@/components/cg'
import { getConfidenceDistribution, getMostChanged, recalculateConfidence } from '@/lib/api-client'
import type { ConfidenceDistribution, ChangedClaim } from '@/types/axion'
import { cn } from '@/lib/utils'

// ─── Pixel-stack visualization ───────────────────────────────────────────────
// Monochrome bar: small square grid cells, filled = cobalt, unfilled =
// low-opacity cobalt on paper. The numeric value is always visible adjacent
// to the stack, so the visualization is never the only source of truth.

const STACK_CELLS = 20

function PixelStack({
  count,
  total,
  label,
}: {
  count: number
  total: number
  label: string
}) {
  const percentage = total > 0 ? (count / total) * 100 : 0
  const filled = total > 0 ? Math.round((count / total) * STACK_CELLS) : 0

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <span className="cg-overline text-ink-muted">{label}</span>
        <span className="cg-mono-meta text-sm text-ink tabular-nums">
          {count.toLocaleString()}{' '}
          <span className="text-ink-muted">({percentage.toFixed(1)}%)</span>
        </span>
      </div>
      <div
        role="img"
        aria-label={`${label}: ${count} of ${total} claims (${percentage.toFixed(1)}%)`}
        className="flex flex-wrap gap-[3px]"
      >
        {Array.from({ length: STACK_CELLS }, (_, i) => (
          <span
            key={i}
            aria-hidden="true"
            className={cn(
              'inline-block h-4 w-[9px] transition-colors duration-300',
              i < filled ? 'cg-cell-filled' : 'cg-cell-empty',
            )}
          />
        ))}
      </div>
    </div>
  )
}

// ─── Changed-claim ledger row ────────────────────────────────────────────────

function ChangedClaimRow({ claim }: { claim: ChangedClaim }) {
  const isPositive = claim.delta > 0

  return (
    <article className="space-y-2 px-4 py-3.5 [&:not(:first-child)]:border-t [&:not(:first-child)]:border-ink/15">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <div className="flex items-center gap-2">
          {/* Sign + arrow glyph carries direction; no color coding */}
          <span
            aria-hidden="true"
            className={cn(
              'inline-block h-2 w-2',
              isPositive ? 'bg-ink' : 'cg-hatch border border-ink',
            )}
          />
          <span
            className={cn(
              'cg-mono-meta text-sm font-semibold text-ink tabular-nums',
            )}
          >
            {isPositive ? '+' : ''}
            {(claim.delta * 100).toFixed(1)}%{' '}
            <span aria-hidden="true">{isPositive ? '↑' : '↓'}</span>
          </span>
          <span className="sr-only">
            {isPositive ? 'increased' : 'decreased'} by {Math.abs(claim.delta * 100).toFixed(1)}%
          </span>
        </div>
        <span className="cg-mono-meta text-xs text-ink-soft tabular-nums">
          {Math.round(claim.base_confidence * 100)}%
          <span aria-hidden="true" className="text-ink-muted"> → </span>
          <span className="font-medium text-ink">
            {Math.round(claim.current_confidence * 100)}%
          </span>
        </span>
      </div>
      <p
        className="line-clamp-2 break-words text-sm leading-relaxed text-ink-soft"
        title={claim.claim_text}
      >
        {claim.claim_text}
      </p>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        {claim.arxiv_id && (
          <a
            href={`https://arxiv.org/abs/${claim.arxiv_id}`}
            target="_blank"
            rel="noopener noreferrer"
            className="cg-mono-meta inline-flex min-w-0 items-center gap-1 text-[10px] text-ink transition-colors hover:bg-ink/5 hover:underline focus-visible:outline-none"
            aria-label={`Open ${claim.paper_title || claim.arxiv_id} on arXiv`}
          >
            <FileText className="h-3 w-3 shrink-0" aria-hidden="true" />
            <span className="max-w-[220px] truncate">
              {claim.paper_title || claim.arxiv_id}
            </span>
            <ExternalLink className="h-2.5 w-2.5 shrink-0 text-ink-muted" aria-hidden="true" />
          </a>
        )}
        {claim.reason && (
          <span className="cg-overline inline-block border border-ink/30 px-1.5 py-0.5 text-ink-muted">
            {claim.reason.replace(/_/g, ' ')}
          </span>
        )}
      </div>
    </article>
  )
}

// ─── Main view ───────────────────────────────────────────────────────────────

export function GraphEvolution() {
  const [isRecalculating, setIsRecalculating] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionNotice, setActionNotice] = useState<string | null>(null)

  const {
    data: distribution,
    isLoading: distLoading,
    error: distError,
    mutate: mutateDistribution,
  } = useSWR<ConfidenceDistribution>(
    'confidence-distribution',
    getConfidenceDistribution,
    { refreshInterval: 60000 }
  )

  const {
    data: changedClaims,
    isLoading: claimsLoading,
    error: claimsError,
    mutate: mutateClaims,
  } = useSWR<ChangedClaim[]>(
    'most-changed',
    () => getMostChanged(10),
    { refreshInterval: 60000 }
  )

  const handleRecalculate = async () => {
    setIsRecalculating(true)
    setActionError(null)
    setActionNotice(null)
    try {
      await recalculateConfidence()
      await Promise.all([mutateDistribution(), mutateClaims()])
      setActionNotice('Claim scores recalculated from stored support and contradiction edges.')
    } catch (error) {
      setActionError(
        error instanceof Error
          ? error.message
          : 'Recalculation failed. Check that write access is configured and Neo4j is available.',
      )
    } finally {
      setIsRecalculating(false)
    }
  }

  const isLoading = distLoading || claimsLoading
  const hasError = distError || claimsError

  return (
    <div className="animate-fade-up space-y-6">
      {/* Header with recalculate action */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Overline className="text-ink-muted">Heuristic score ledger</Overline>
        <Button
          onClick={handleRecalculate}
          disabled={isRecalculating}
          variant="outline"
          size="sm"
        >
          {isRecalculating ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          <span>{isRecalculating ? 'Recalculating…' : 'Recalculate'}</span>
        </Button>
      </div>

      <p className="border-l-2 border-ink/30 pl-3 text-[11px] leading-relaxed text-ink-soft">
        Claim scores are a deterministic heuristic updated from support and
        contradiction edges. They are not calibrated probabilities, model
        confidence, or human review. Recalculation writes new scores to the graph.
      </p>

      <div aria-live="polite">
        {actionNotice && !actionError && (
          <p className="border border-ink/30 bg-ink/5 px-3 py-2 text-xs text-ink">
            {actionNotice}
          </p>
        )}
        {actionError && (
          <ErrorBanner title="Recalculation failed" message={actionError} />
        )}
      </div>

      {/* Error state */}
      {hasError && (
        <ErrorBanner
          title="Heuristic score data unavailable"
          message="Failed to load the score distribution or changed-claim ledger. Is the API running?"
        />
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Confidence Distribution */}
        <section className="border border-ink/25 bg-paper p-5">
          <div className="mb-5 flex items-center gap-2.5 border-b border-ink/20 pb-3">
            <Overline as="h3" className="tracking-[0.1em] text-ink">
              Heuristic score distribution
            </Overline>
          </div>

          <p className="mb-4 text-[11px] leading-relaxed text-ink-soft">
            Buckets of stored claim scores, not an accuracy or agreement measure.
          </p>

          {isLoading ? (
            <div className="space-y-5">
              {[1, 2, 3].map((i) => (
                <div key={i} className="space-y-2">
                  <span className="cg-skeleton block h-3.5 w-2/3" />
                  <span className="cg-skeleton block h-4 w-full" />
                </div>
              ))}
              <div className="border-t border-ink/15 pt-4">
                <span className="cg-skeleton block h-3.5 w-full" />
                <span className="cg-skeleton mt-2 block h-3.5 w-1/2" />
              </div>
            </div>
          ) : distribution && distribution.total > 0 ? (
            <>
              <div className="space-y-5">
                <PixelStack label="High (≥80%)" count={distribution.high} total={distribution.total} />
                <PixelStack label="Medium (50–79%)" count={distribution.medium} total={distribution.total} />
                <PixelStack label="Low (<50%)" count={distribution.low} total={distribution.total} />
              </div>

              <div className="mt-5 space-y-2 border-t border-ink/25 pt-4">
                <div className="flex items-center justify-between gap-4 text-sm">
                  <Overline className="text-ink-muted">Total claims scored</Overline>
                  <span className="cg-mono-meta text-ink tabular-nums">
                    {distribution.total.toLocaleString()}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-4 text-sm">
                  <Overline className="text-ink-muted">Mean heuristic score</Overline>
                  <span className="cg-mono-meta text-ink tabular-nums">
                    {Math.round(distribution.average * 100)}%
                  </span>
                </div>
              </div>
            </>
          ) : (
            <p className="py-8 text-center text-sm leading-relaxed text-ink-soft">
              No claim scores are available yet. Ingest claims and run recalculation
              after support or contradiction edges exist.
            </p>
          )}
        </section>

        {/* Most Changed Claims */}
        <section className="border border-ink/25 bg-paper p-5">
          <div className="mb-2 flex items-center gap-2.5 border-b border-ink/20 pb-3">
            <Overline as="h3" className="tracking-[0.1em] text-ink">
              Most changed claims
            </Overline>
          </div>

          <p className="mb-2 text-[11px] leading-relaxed text-ink-soft">
            Largest absolute movement from the stored baseline score.
          </p>

          {isLoading ? (
            <div className="space-y-3 pt-3">
              {[1, 2, 3].map((i) => (
                <span key={i} className="cg-skeleton block h-16 w-full" />
              ))}
            </div>
          ) : changedClaims && changedClaims.length > 0 ? (
            <div className="-mx-1 max-h-[420px] overflow-y-auto">
              {changedClaims.map((claim) => (
                <ChangedClaimRow key={claim.claim_id} claim={claim} />
              ))}
            </div>
          ) : (
            <div className="py-10 text-center">
              <span className="cg-mono-meta text-sm text-ink-muted" aria-hidden="true">
                [ NO BASELINE ]
              </span>
              <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-ink-soft">
                No claims have a stored baseline score to compare against. Run
                recalculation after the graph contains support or contradiction edges.
              </p>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
