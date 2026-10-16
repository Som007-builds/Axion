'use client'

import { useState } from 'react'
import { Search, Loader2, Calendar, FileText, CheckCircle, XCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Slider } from '@/components/ui/slider'
import { getEvolution, getDisputes } from '@/lib/api-client'
import type { TemporalEvolution, DisputeTimeline, YearlyPosition, Dispute } from '@/types/axion'

function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.8) return 'bg-[#10b981]'
  if (confidence >= 0.5) return 'bg-[#f59e0b]'
  return 'bg-[#f43f5e]'
}

function getConfidenceBorder(confidence: number): string {
  if (confidence >= 0.8) return 'border-l-[#10b981]'
  if (confidence >= 0.5) return 'border-l-[#f59e0b]'
  return 'border-l-[#f43f5e]'
}

function YearlyPositionCard({ position }: { position: YearlyPosition }) {
  return (
    <div className="relative flex gap-4">
      {/* Timeline rail */}
      <div className="flex flex-col items-center">
        <div className="flex h-10 w-10 items-center justify-center rounded-full border border-[var(--axion-border-subtle)] bg-[var(--axion-surface-2)]">
          <span className="text-sm font-medium text-[#f0f6ff] tabular-nums">{position.year}</span>
        </div>
        <div className="flex-1 w-px bg-gradient-to-b from-[var(--axion-border-subtle)] to-transparent" />
      </div>
      
      {/* Content */}
      <div className="flex-1 pb-6">
        <div className={`rounded-xl border border-[var(--axion-border-subtle)] border-l-2 ${getConfidenceBorder(position.confidence)} axion-surface p-4 space-y-3 axion-card-hover`}>
          <div className="flex items-center gap-3">
            <div className={`h-2 w-2 rounded-full ${getConfidenceColor(position.confidence)}`} />
            <span className="text-xs text-[#475569] font-mono tabular-nums">
              {Math.round(position.confidence * 100)}% confidence
            </span>
          </div>
          <p className="text-sm text-[#f0f6ff] leading-relaxed">{position.position}</p>
          {position.key_papers.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {position.key_papers.map((paper, i) => (
                <Badge
                  key={i}
                  variant="outline"
                  className="border-[var(--axion-border-subtle)] bg-transparent font-mono text-[10px] text-[#8b5cf6]"
                >
                  <FileText className="mr-1 h-2.5 w-2.5" />
                  {paper}
                </Badge>
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
    <div className="rounded-xl border border-[var(--axion-border-subtle)] axion-surface p-4 space-y-3 axion-card-hover">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Calendar className="h-3.5 w-3.5 text-[#3b82f6]" />
          <span className="text-xs text-[#94a3b8] font-mono tabular-nums">{duration}</span>
        </div>
        <Badge
          variant="outline"
          className={`${
            dispute.resolved
              ? 'border-[#10b981]/20 bg-[#10b981]/8 text-[#10b981]'
              : 'border-[#f59e0b]/20 bg-[#f59e0b]/8 text-[#f59e0b]'
          }`}
        >
          {dispute.resolved ? (
            <>
              <CheckCircle className="mr-1 h-3 w-3" />
              Resolved
            </>
          ) : (
            <>
              <XCircle className="mr-1 h-3 w-3" />
              Ongoing
            </>
          )}
        </Badge>
      </div>
      
      <p className="text-sm text-[#f0f6ff] leading-relaxed">{dispute.topic}</p>
      
      {dispute.resolution && (
        <div className="rounded-lg border border-[#10b981]/15 bg-[#10b981]/5 p-3">
          <p className="text-sm text-[#10b981]">{dispute.resolution}</p>
        </div>
      )}
      
      {dispute.key_claims.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {dispute.key_claims.map((claimId, i) => (
            <span
              key={i}
              className="font-mono text-[10px] text-[#a78bfa] rounded-md bg-[#8b5cf6]/8 border border-[#8b5cf6]/15 px-2 py-0.5"
            >
              {claimId}
            </span>
          ))}
        </div>
      )}
    </div>
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
      <div className="space-y-4 rounded-xl border border-[var(--axion-border-subtle)] axion-surface p-5">
        <div className="flex gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-[#334155]" />
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="Enter a research topic... e.g., transformer scaling laws"
              className="w-full rounded-lg border border-[var(--axion-border-subtle)] bg-[var(--axion-surface-2)] pl-9 pr-4 py-2 text-sm text-[#f0f6ff] placeholder:text-[#334155] focus:border-[#3b82f6]/40 focus:outline-none focus:ring-1 focus:ring-[#3b82f6]/20 transition-all duration-200"
            />
          </div>
          <Button
            onClick={handleSearch}
            disabled={!topic.trim() || isLoading}
            className="border border-[#3b82f6]/40 bg-[#3b82f6]/5 text-[#60a5fa] hover:bg-[#3b82f6]/10 transition-all duration-150"
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Search className="h-4 w-4" />
            )}
            <span>Search</span>
          </Button>
        </div>
        
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2 text-sm text-[#94a3b8]">
            <span>Year range:</span>
            <span className="font-mono text-[#f0f6ff] tabular-nums">
              {yearRange[0]} — {yearRange[1]}
            </span>
          </div>
          <Slider
            value={yearRange}
            onValueChange={setYearRange}
            min={2015}
            max={2026}
            step={1}
            className="flex-1"
          />
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="rounded-xl border border-[#f43f5e]/20 bg-[#f43f5e]/5 p-4 animate-fade-up">
          <p className="text-sm text-[#f43f5e]">{error}</p>
        </div>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="rounded-xl border border-[var(--axion-border-subtle)] axion-surface p-6 animate-fade-up">
          <div className="flex items-center gap-3">
            <Loader2 className="h-5 w-5 animate-spin text-[#3b82f6]" />
            <span className="text-sm text-[#94a3b8]">
              Analyzing temporal evolution for &quot;{topic}&quot;...
            </span>
          </div>
        </div>
      )}

      {/* Results */}
      {evolution && !isLoading && (
        <div className="grid gap-6 lg:grid-cols-2 animate-fade-up">
          {/* Evolution timeline */}
          <div className="space-y-4">
            <h3 className="text-base font-medium text-[#f0f6ff]">
              Evolution of &quot;{evolution.topic}&quot;
            </h3>
            
            {/* Narrative */}
            <div className="rounded-xl border border-[var(--axion-border-subtle)] axion-surface axion-inner-glow p-5">
              <h4 className="mb-2 text-[10px] font-medium uppercase tracking-wider text-[#475569]">
                Narrative Summary
              </h4>
              <p className="text-sm text-[#94a3b8] leading-relaxed">{evolution.narrative}</p>
            </div>

            {/* Current status */}
            <div className="rounded-xl border border-[#3b82f6]/15 bg-[#3b82f6]/[0.03] p-5">
              <h4 className="mb-2 text-[10px] font-medium uppercase tracking-wider text-[#3b82f6]">
                Current Status
              </h4>
              <p className="text-sm text-[#f0f6ff] leading-relaxed">{evolution.current_status}</p>
            </div>

            {/* Timeline */}
            <div className="pt-4 stagger-children">
              {evolution.yearly_positions.map((pos) => (
                <YearlyPositionCard key={pos.year} position={pos} />
              ))}
            </div>
          </div>

          {/* Disputes */}
          <div className="space-y-4">
            <h3 className="text-base font-medium text-[#f0f6ff]">
              Scientific Disputes
            </h3>
            
            {disputes && disputes.disputes.length > 0 ? (
              <div className="space-y-4 stagger-children">
                {disputes.disputes.map((dispute) => (
                  <DisputeCard key={dispute.id} dispute={dispute} />
                ))}
              </div>
            ) : (
              <div className="rounded-xl border border-[var(--axion-border-subtle)] axion-surface p-8 text-center">
                <CheckCircle className="mx-auto h-8 w-8 text-[#10b981]" />
                <p className="mt-3 text-sm text-[#94a3b8]">
                  No major scientific disputes found for this topic
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!evolution && !isLoading && !error && (
        <div className="rounded-xl border border-[var(--axion-border-subtle)] axion-surface p-12 text-center">
          <Calendar className="mx-auto h-12 w-12 text-[#334155]" />
          <h3 className="mt-4 text-lg font-medium text-[#f0f6ff]">
            Explore Scientific Evolution
          </h3>
          <p className="mt-2 text-sm text-[#94a3b8]">
            Enter a research topic to see how scientific consensus has evolved over time
          </p>
        </div>
      )}
    </div>
  )
}
