'use client'

import { useState } from 'react'
import { Search, Loader2, FileText, Calendar } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import { Overline, StatusChip, ConfidenceTag, ErrorBanner, EmptyState } from '@/components/cg'
import { getEvolution, getDisputes } from '@/lib/api-client'
import type { TemporalEvolution, DisputeTimeline, YearlyPosition, Dispute } from '@/types/axion'

function YearlyPositionCard({ position }: { position: YearlyPosition }) {
  return (
    <div className="relative flex gap-4">
      {/* Timeline rail */}
      <div className="flex flex-col items-center">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center border border-ink/40 bg-paper-secondary/60">
          <span className="cg-mono-meta text-xs font-medium text-ink tabular-nums">
            {position.year}
          </span>
        </div>
        <div aria-hidden="true" className="w-px flex-1 bg-ink/25" />
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1 pb-6">
        <div className="space-y-2.5 border-l-[1.5px] border-ink/30 pl-4">
          <ConfidenceTag value={position.confidence} />
          <p className="text-[15px] leading-relaxed text-ink">{position.position}</p>
          {position.key_papers.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {position.key_papers.map((paper, i) => (
                <span
                  key={i}
                  className="cg-mono-meta inline-flex items-center gap-1 border border-ink/30 bg-ink/[0.04] px-2 py-0.5 text-[10px] text-ink"
                >
                  <FileText className="h-2.5 w-2.5" aria-hidden="true" />
                  {paper}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function DisputeCard({ dispute }: { dispute: Dispute }) {
  const startLabel = dispute.start_year ?? 'Unknown start'
  const duration = dispute.end_year
    ? `${startLabel} — ${dispute.end_year}`
    : `${startLabel} — ongoing`

  return (
    <article className="space-y-3 px-1 py-4 [&:not(:first-child)]:border-t [&:not(:first-child)]:border-ink/15">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5">
        <div className="flex items-center gap-2">
          <Calendar className="h-3.5 w-3.5 text-ink/50" aria-hidden="true" />
          <span className="cg-mono-meta text-xs text-ink tabular-nums">{duration}</span>
        </div>
        <StatusChip status={dispute.resolved ? 'resolved' : 'ongoing'} />
      </div>

      <p className="text-[15px] leading-relaxed text-ink">{dispute.topic}</p>

      {dispute.resolution && (
        <div className="border-l-2 border-ink/40 bg-ink/[0.03] p-3">
          <p className="text-sm leading-relaxed text-ink">{dispute.resolution}</p>
        </div>
      )}

      {dispute.key_claims.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {dispute.key_claims.map((claimId, i) => (
            <span
              key={i}
              className="cg-mono-meta border border-ink/30 bg-ink/[0.04] px-2 py-0.5 text-[10px] text-ink"
            >
              {claimId}
            </span>
          ))}
        </div>
      )}
    </article>
  )
}

export function TimelineView() {
  const [topic, setTopic] = useState('')
  const [yearRange, setYearRange] = useState([2020, 2026])
  const [isLoading, setIsLoading] = useState(false)
  const [evolution, setEvolution] = useState<TemporalEvolution | null>(null)
  const [disputes, setDisputes] = useState<DisputeTimeline | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleSearch = async () => {
    if (!topic.trim()) return

    setIsLoading(true)
    setError(null)

    try {
      const [evoResult, disputeResult] = await Promise.all([
        getEvolution(topic.trim(), yearRange[0], yearRange[1]),
        getDisputes(topic.trim()),
      ])
      setEvolution(evoResult)
      setDisputes(disputeResult)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load timeline data')
      setEvolution(null)
      setDisputes(null)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Search controls */}
      <div className="space-y-4 border border-ink/30 bg-paper p-5">
        <div className="flex flex-col gap-3 sm:flex-row">
          <div className="relative min-w-0 flex-1">
            <Search
              className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink/40"
              aria-hidden="true"
            />
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="Enter a research topic... e.g., transformer scaling laws"
              aria-label="Research topic"
              className="h-10 w-full border border-ink/40 bg-paper pl-9 pr-4 text-sm text-ink placeholder:text-ink/35 transition-colors duration-150 hover:border-ink/60 focus:border-ink focus:ring-[3px] focus:ring-ink/15 focus:outline-none"
            />
          </div>
          <Button
            onClick={handleSearch}
            disabled={!topic.trim() || isLoading}
            variant="outline"
            aria-label="Analyze topic evolution"
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Search className="h-4 w-4" aria-hidden="true" />
            )}
            <span>Search</span>
          </Button>
        </div>

        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <div className="flex items-center gap-2">
            <Overline className="text-ink/60">Year range</Overline>
            <span className="cg-mono-meta text-sm text-ink tabular-nums">
              {yearRange[0]} — {yearRange[1]}
            </span>
          </div>
          <Slider
            value={yearRange}
            onValueChange={setYearRange}
            min={2015}
            max={2026}
            step={1}
            aria-label="Year range"
            className="min-w-[200px] flex-1"
          />
        </div>
      </div>

      {/* Error state */}
      {error && (
        <ErrorBanner
          title="Timeline unavailable"
          message={error}
          className="animate-fade-up"
        />
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="animate-fade-up flex items-center gap-3 border border-ink/40 bg-paper p-5">
          <Loader2 className="h-4 w-4 animate-spin text-ink" aria-hidden="true" />
          <span className="text-sm text-ink-soft">
            Analyzing temporal evolution for &quot;{topic}&quot;…
          </span>
        </div>
      )}

      {/* Results */}
      {evolution && !isLoading && (
        <div className="grid gap-8 lg:grid-cols-2 animate-fade-up">
          {/* Evolution timeline */}
          <div className="min-w-0 space-y-4">
            <h2 className="cg-display truncate text-2xl text-ink">
              Evolution of &quot;{evolution.topic}&quot;
            </h2>

            {/* Narrative */}
            <div className="border border-ink/25 bg-paper p-5">
              <Overline className="text-ink/60">Narrative Summary</Overline>
              <p className="mt-2.5 max-w-[var(--cg-reading-max)] text-sm leading-relaxed text-ink-soft">
                {evolution.narrative}
              </p>
            </div>

            {/* Current status */}
            <div className="border-[1.5px] border-ink/60 bg-paper p-5">
              <Overline className="text-ink">Current Status</Overline>
              <p className="mt-2.5 text-[15px] leading-relaxed text-ink">
                {evolution.current_status}
              </p>
            </div>

            {/* Timeline */}
            <div className="pt-3">
              {evolution.yearly_positions.map((pos) => (
                <YearlyPositionCard key={pos.year} position={pos} />
              ))}
            </div>
          </div>

          {/* Disputes */}
          <div className="min-w-0 space-y-4">
            <h2 className="cg-display text-2xl text-ink">Scientific Disputes</h2>

            {disputes && disputes.disputes.length > 0 ? (
              <div className="border border-ink/25 bg-paper px-4 py-1">
                {disputes.disputes.map((dispute) => (
                  <DisputeCard key={dispute.id} dispute={dispute} />
                ))}
              </div>
            ) : (
              <div className="border border-ink/25 bg-paper px-6 py-8 text-center">
                <span className="cg-mono-meta text-2xl text-ink/40" aria-hidden="true">
                  ✓
                </span>
                <p className="mt-2 text-sm leading-relaxed text-ink-soft">
                  No major scientific disputes found for this topic
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!evolution && !isLoading && !error && (
        <EmptyState
          glyph="⌛"
          title="Explore Scientific Evolution"
          description="Enter a research topic to see how scientific consensus has evolved over time."
        />
      )}
    </div>
  )
}
