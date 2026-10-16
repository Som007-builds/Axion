'use client'

import { useState, useEffect } from 'react'
import { Loader2, FlaskConical, AlertTriangle, Clock, DollarSign, Database, Target } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { getExperiment, designExperiment } from '@/lib/api-client'
import type { Experiment } from '@/types/axion'

function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.8) return 'text-[#10b981]'
  if (confidence >= 0.5) return 'text-[#f59e0b]'
  return 'text-[#f43f5e]'
}

interface ExperimentCardProps {
  contradictionId: string
  hasExperiment?: boolean
}

export function ExperimentCard({ contradictionId, hasExperiment }: ExperimentCardProps) {
  const [experiment, setExperiment] = useState<Experiment | null>(null)
  // Start in the loading state when the caller already knows an experiment
  // exists, so the effect below does not need to set state synchronously.
  const [isLoading, setIsLoading] = useState(!!hasExperiment)
  const [isDesigning, setIsDesigning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasFetched, setHasFetched] = useState(false)

  // Auto-fetch the stored experiment when the caller knows one exists.
  // NOTE: this used to run in the render body, firing a request on every render.
  useEffect(() => {
    if (!hasExperiment || hasFetched) return
    let cancelled = false
    getExperiment(contradictionId)
      .then((exp) => {
        if (cancelled) return
        setExperiment(exp)
        setHasFetched(true)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load experiment')
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [hasExperiment, hasFetched, contradictionId])

  const handleDesign = async () => {
    setIsDesigning(true)
    setError(null)
    try {
      const exp = await designExperiment(contradictionId)
      setExperiment(exp)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to design experiment')
    } finally {
      setIsDesigning(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-4 text-[#94a3b8]">
        <Loader2 className="h-4 w-4 animate-spin text-[#3b82f6]" />
        <span className="text-sm">Loading experiment...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-lg border border-[#f43f5e]/20 bg-[#f43f5e]/5 p-3">
        <p className="text-sm text-[#f43f5e]">{error}</p>
      </div>
    )
  }

  if (!experiment) {
    return (
      <div className="flex items-center justify-between rounded-lg border border-[var(--axion-border-subtle)] bg-[var(--axion-surface-2)] p-4">
        <div className="flex items-center gap-2 text-[#94a3b8]">
          <FlaskConical className="h-4 w-4" />
          <span className="text-sm">No experiment designed yet</span>
        </div>
        <Button
          onClick={handleDesign}
          disabled={isDesigning}
          variant="outline"
          size="sm"
          className="border-[#3b82f6]/30 bg-[#3b82f6]/5 text-[#60a5fa] hover:bg-[#3b82f6]/10 hover:text-white transition-all duration-150"
        >
          {isDesigning ? (
            <>
              <Loader2 className="h-3 w-3 animate-spin" />
              <span>Designing...</span>
            </>
          ) : (
            <>
              <FlaskConical className="h-3 w-3" />
              <span>Design Experiment</span>
            </>
          )}
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-4 rounded-xl border border-[var(--axion-border-subtle)] axion-surface p-5 animate-fade-up">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#3b82f6]/10">
            <FlaskConical className="h-4 w-4 text-[#3b82f6]" />
          </div>
          <h4 className="font-medium text-[#f0f6ff]">{experiment.title}</h4>
        </div>
        <Badge
          variant="outline"
          className={`border-[var(--axion-border-subtle)] bg-transparent tabular-nums ${getConfidenceColor(experiment.design_confidence)}`}
        >
          {Math.round(experiment.design_confidence * 100)}% design confidence
        </Badge>
      </div>

      {/* Hypotheses */}
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-[var(--axion-border-subtle)] border-l-2 border-l-[#10b981] bg-[var(--axion-surface-2)] p-4">
          <h5 className="mb-2 text-[10px] font-medium uppercase tracking-wider text-[#10b981]">
            Hypothesis A
          </h5>
          <p className="text-sm text-[#94a3b8] leading-relaxed">{experiment.hypothesis_a}</p>
        </div>
        <div className="rounded-lg border border-[var(--axion-border-subtle)] border-l-2 border-l-[#f43f5e] bg-[var(--axion-surface-2)] p-4">
          <h5 className="mb-2 text-[10px] font-medium uppercase tracking-wider text-[#f43f5e]">
            Hypothesis B
          </h5>
          <p className="text-sm text-[#94a3b8] leading-relaxed">{experiment.hypothesis_b}</p>
        </div>
      </div>

      {/* Procedure */}
      <div>
        <h5 className="mb-2 text-[10px] font-medium uppercase tracking-wider text-[#475569]">
          Procedure
        </h5>
        {(() => {
          const lines = experiment.procedure.split(/\r?\n/).map(l => l.trim()).filter(Boolean)
          if (lines.length <= 1) {
            return <p className="text-sm text-[#94a3b8] leading-relaxed">{experiment.procedure}</p>
          }
          return (
            <div className="space-y-2">
              {lines.map((line, i) => {
                const clean = line.replace(/^\d+[\.)\s]*/, '')
                return (
                  <div key={i} className="flex items-start gap-3">
                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#3b82f6]/10 font-mono text-[10px] text-[#3b82f6]">
                      {i + 1}
                    </span>
                    <p className="text-sm text-[#94a3b8] leading-relaxed">{clean}</p>
                  </div>
                )
              })}
            </div>
          )
        })()}
      </div>

      {/* Metrics Row */}
      <div className="flex flex-wrap gap-3 rounded-lg border border-[var(--axion-border-subtle)] bg-[var(--axion-surface-2)] p-3">
        <div className="flex items-center gap-1.5 text-xs text-[#94a3b8]">
          <Database className="h-3.5 w-3.5 text-[#8b5cf6]" />
          <span>{experiment.dataset}</span>
        </div>
        <div className="h-4 w-px bg-[var(--axion-border-subtle)]" />
        <div className="flex items-center gap-1.5 text-xs text-[#94a3b8]">
          <Clock className="h-3.5 w-3.5 text-[#3b82f6]" />
          <span>{experiment.duration}</span>
        </div>
        <div className="h-4 w-px bg-[var(--axion-border-subtle)]" />
        <div className="flex items-center gap-1.5 text-xs text-[#94a3b8]">
          <DollarSign className="h-3.5 w-3.5 text-[#10b981]" />
          <span>{experiment.cost}</span>
        </div>
        {experiment.metric && (
          <>
            <div className="h-4 w-px bg-[var(--axion-border-subtle)]" />
            <div className="flex items-center gap-1.5 text-xs text-[#94a3b8]">
              <Target className="h-3.5 w-3.5 text-[#a78bfa]" />
              <span>{experiment.metric}</span>
            </div>
          </>
        )}
      </div>

      {/* Decision Rule */}
      <div className="rounded-lg border border-[#3b82f6]/15 bg-[#3b82f6]/[0.03] p-4">
        <h5 className="mb-2 text-[10px] font-medium uppercase tracking-wider text-[#3b82f6]">
          Decision Rule
        </h5>
        <p className="text-sm text-[#f0f6ff] leading-relaxed">{experiment.decision_rule}</p>
      </div>

      {/* Caveats */}
      {experiment.caveats && experiment.caveats.length > 0 && (
        <div className="rounded-lg border border-[#f59e0b]/15 bg-[#f59e0b]/[0.03] p-4">
          <div className="mb-2 flex items-center gap-2">
            <AlertTriangle className="h-3.5 w-3.5 text-[#f59e0b]" />
            <h5 className="text-[10px] font-medium uppercase tracking-wider text-[#f59e0b]">
              Caveats
            </h5>
          </div>
          <ul className="list-inside list-disc space-y-1 text-sm text-[#94a3b8]">
            {experiment.caveats.map((caveat, i) => (
              <li key={i} className="leading-relaxed">{caveat}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
