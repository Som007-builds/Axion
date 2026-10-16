'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { ChevronDown, ChevronRight, AlertTriangle, FileText } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Slider } from '@/components/ui/slider'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { ExperimentCard } from './experiment-card'
import { getContradictions } from '@/lib/api-client'
import type { Contradiction, ContradictionsResponse } from '@/types/axion'

function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.8) return 'text-[#10b981]'
  if (confidence >= 0.5) return 'text-[#f59e0b]'
  return 'text-[#f43f5e]'
}

function getConfidenceBg(confidence: number): string {
  if (confidence >= 0.8) return 'bg-[#10b981]/10 border-[#10b981]/20'
  if (confidence >= 0.5) return 'bg-[#f59e0b]/10 border-[#f59e0b]/20'
  return 'bg-[#f43f5e]/10 border-[#f43f5e]/20'
}

function ContradictionCard({ contradiction }: { contradiction: Contradiction }) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className="rounded-xl border border-[var(--axion-border-subtle)] axion-surface axion-card-hover">
        <CollapsibleTrigger className="flex w-full items-start gap-4 p-5 text-left transition-colors duration-150 hover:bg-[rgba(59,130,246,0.03)] rounded-xl">
          <div className="mt-1">
            {isOpen ? (
              <ChevronDown className="h-4 w-4 text-[#475569]" />
            ) : (
              <ChevronRight className="h-4 w-4 text-[#475569]" />
            )}
          </div>
          <div className="flex-1 space-y-2">
            <div className="flex items-center gap-3">
              <AlertTriangle className="h-4 w-4 text-[#f43f5e]" />
              <Badge
                variant="outline"
                className={`border ${getConfidenceBg(contradiction.confidence)} ${getConfidenceColor(contradiction.confidence)} tabular-nums`}
              >
                {Math.round(contradiction.confidence * 100)}%
              </Badge>
              {contradiction.has_experiment && (
                <Badge
                  variant="outline"
                  className="border-[#3b82f6]/20 bg-[#3b82f6]/8 text-[#60a5fa]"
                >
                  Has experiment
                </Badge>
              )}
            </div>
            <p className="text-sm text-[#94a3b8] line-clamp-2">
              {contradiction.explanation}
            </p>
          </div>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <div className="border-t border-[var(--axion-border-subtle)] p-5 space-y-4 animate-fade-up">
            {/* Claims side by side with VS badge */}
            <div className="relative grid gap-4 md:grid-cols-2">
              <div className="rounded-lg border border-[var(--axion-border-subtle)] bg-[var(--axion-surface-2)] p-4 border-l-2 border-l-[#3b82f6]">
                <div className="mb-2 flex items-center gap-2">
                  <FileText className="h-4 w-4 text-[#8b5cf6]" />
                  <span className="font-mono text-xs text-[#8b5cf6]">
                    {contradiction.paper_a}
                  </span>
                </div>
                <p className="text-sm text-[#f0f6ff]">{contradiction.claim_a.text}</p>
                <div className="mt-2 flex items-center gap-2 text-xs text-[#475569]">
                  <span>{contradiction.claim_a.section}</span>
                  <span className="text-[var(--axion-border-subtle)]">|</span>
                  <span className={getConfidenceColor(contradiction.claim_a.confidence)}>
                    {Math.round(contradiction.claim_a.confidence * 100)}%
                  </span>
                </div>
              </div>

              {/* VS Badge */}
              <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-10 hidden md:flex">
                <div className="flex h-8 w-8 items-center justify-center rounded-full border border-[#f43f5e]/30 bg-[#f43f5e]/10 text-[10px] font-bold text-[#f43f5e]">
                  VS
                </div>
              </div>

              <div className="rounded-lg border border-[var(--axion-border-subtle)] bg-[var(--axion-surface-2)] p-4 border-l-2 border-l-[#f43f5e]">
                <div className="mb-2 flex items-center gap-2">
                  <FileText className="h-4 w-4 text-[#8b5cf6]" />
                  <span className="font-mono text-xs text-[#8b5cf6]">
                    {contradiction.paper_b}
                  </span>
                </div>
                <p className="text-sm text-[#f0f6ff]">{contradiction.claim_b.text}</p>
                <div className="mt-2 flex items-center gap-2 text-xs text-[#475569]">
                  <span>{contradiction.claim_b.section}</span>
                  <span className="text-[var(--axion-border-subtle)]">|</span>
                  <span className={getConfidenceColor(contradiction.claim_b.confidence)}>
                    {Math.round(contradiction.claim_b.confidence * 100)}%
                  </span>
                </div>
              </div>
            </div>

            {/* Full explanation */}
            <div>
              <h5 className="mb-2 text-xs font-medium uppercase tracking-wider text-[#475569]">
                Explanation
              </h5>
              <p className="text-sm text-[#94a3b8]">{contradiction.explanation}</p>
            </div>

            {/* Experiment */}
            <div className="pt-2">
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
    <div className="rounded-xl border border-[var(--axion-border-subtle)] axion-surface p-5 space-y-3">
      <div className="flex items-center gap-3">
        <div className="animate-shimmer h-5 w-5 rounded" />
        <div className="animate-shimmer h-5 w-16 rounded" />
      </div>
      <div className="animate-shimmer h-4 w-full rounded" />
      <div className="animate-shimmer h-4 w-3/4 rounded" />
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
      <div className="flex items-center gap-6 rounded-xl border border-[var(--axion-border-subtle)] axion-surface p-4">
        <div className="flex items-center gap-2 text-sm text-[#94a3b8]">
          <span>Min confidence:</span>
          <span className="font-mono text-[#f0f6ff] tabular-nums">{minConfidence}%</span>
        </div>
        <Slider
          value={[minConfidence]}
          onValueChange={([value]) => setMinConfidence(value)}
          min={0}
          max={100}
          step={5}
          className="flex-1"
        />
      </div>

      {/* Error state */}
      {error && (
        <div className="rounded-xl border border-[#f43f5e]/20 bg-[#f43f5e]/5 p-4">
          <p className="text-sm text-[#f43f5e]">
            Failed to load contradictions. Is the API running?
          </p>
        </div>
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
          <div className="flex items-center justify-between">
            <p className="text-sm text-[#475569]">
              {data.total} contradiction{data.total !== 1 ? 's' : ''} detected
            </p>
          </div>
          <div className="space-y-4 stagger-children">
            {data.contradictions.map((c) => (
              <ContradictionCard key={c.id} contradiction={c} />
            ))}
          </div>
          {data.contradictions.length === 0 && (
            <div className="rounded-xl border border-[var(--axion-border-subtle)] axion-surface p-8 text-center">
              <AlertTriangle className="mx-auto h-8 w-8 text-[#334155]" />
              <p className="mt-3 text-[#94a3b8]">
                No contradictions found with confidence above {minConfidence}%
              </p>
            </div>
          )}
        </>
      )}
    </div>
  )
}
