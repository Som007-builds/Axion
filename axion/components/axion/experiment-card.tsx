'use client'

import { useState, useEffect } from 'react'
import {
  Loader2,
  FlaskConical,
  Clock,
  DollarSign,
  Database,
  Target,
  AlertTriangle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Overline, ConfidenceTag, ErrorBanner } from '@/components/cg'
import { getExperiment, designExperiment } from '@/lib/api-client'
import type { Experiment } from '@/types/axion'

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
      <div className="flex items-center gap-2 py-3 text-ink-soft">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-ink" aria-hidden="true" />
        <span className="cg-mono-meta text-xs">Loading experiment…</span>
      </div>
    )
  }

  if (error) {
    return <ErrorBanner title="Experiment unavailable" message={error} />
  }

  if (!experiment) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 border border-ink/30 bg-paper-secondary/60 p-4">
        <div className="flex items-center gap-2.5 text-ink-soft">
          <FlaskConical className="h-4 w-4 text-ink" aria-hidden="true" />
          <span className="text-sm">No experiment designed yet</span>
        </div>
        <Button
          onClick={handleDesign}
          disabled={isDesigning}
          variant="outline"
          size="sm"
        >
          {isDesigning ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              <span>Designing…</span>
            </>
          ) : (
            <>
              <FlaskConical className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Design Experiment</span>
            </>
          )}
        </Button>
      </div>
    )
  }

  return (
    <div className="animate-fade-up space-y-4 border-[1.5px] border-ink/50 bg-paper p-5">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-6 w-6 items-center justify-center bg-ink text-paper">
            <FlaskConical className="h-3.5 w-3.5" aria-hidden="true" />
          </div>
          <h3 className="cg-display text-lg leading-snug text-ink">{experiment.title}</h3>
        </div>
        <ConfidenceTag value={experiment.design_confidence} />
      </div>

      {/* Hypotheses */}
      <div className="grid gap-4 md:grid-cols-2">
        <div className="min-w-0 border-t-[1.5px] border-ink bg-paper-secondary/60 p-4">
          <div className="mb-2 flex items-center gap-2">
            <span aria-hidden="true" className="inline-block h-2 w-2 bg-ink" />
            <Overline className="text-ink/60">Hypothesis A</Overline>
          </div>
          <p className="text-sm leading-relaxed text-ink-soft">{experiment.hypothesis_a}</p>
        </div>
        <div className="min-w-0 border-t-[1.5px] border-ink/30 p-4">
          <div className="mb-2 flex items-center gap-2">
            <span aria-hidden="true" className="inline-block h-2 w-2 border border-ink/70" />
            <Overline className="text-ink/60">Hypothesis B</Overline>
          </div>
          <p className="text-sm leading-relaxed text-ink-soft">{experiment.hypothesis_b}</p>
        </div>
      </div>

      {/* Procedure */}
      <div>
        <Overline className="text-ink/60">Procedure</Overline>
        <div className="mt-2.5 flex flex-col gap-2">
          {experiment.procedure
            .split(/\r?\n/)
            .map((l) => l.trim())
            .filter(Boolean)
            .map((line, i, all) => {
              if (all.length <= 1) return (
                <p key={i} className="text-sm leading-relaxed text-ink-soft">{line}</p>
              )
              const clean = line.replace(/^\d+[\.)\s]*/, '')
              return (
                <div key={i} className="flex items-start gap-3">
                  <span className="cg-mono-meta mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center border border-ink/50 text-[10px] text-ink">
                    {i + 1}
                  </span>
                  <p className="text-sm leading-relaxed text-ink-soft">{clean}</p>
                </div>
              )
            })}
        </div>
      </div>

      {/* Metrics row */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border border-ink/25 bg-paper-secondary/50 p-3">
        <MetricItem icon={Database} label={experiment.dataset} />
        <MetricItem icon={Clock} label={experiment.duration} />
        <MetricItem icon={DollarSign} label={experiment.cost} />
        <MetricItem icon={Target} label={experiment.metric} />
      </div>

      {/* Decision rule */}
      {experiment.decision_rule && (
        <div className="border border-ink/40 bg-ink/[0.03] p-4">
          <Overline className="text-ink">Decision Rule</Overline>
          <p className="mt-1.5 text-sm leading-relaxed text-ink">{experiment.decision_rule}</p>
        </div>
      )}

      {/* Caveats */}
      {experiment.caveats && experiment.caveats.length > 0 && (
        <div className="border border-ink/30 bg-paper p-4">
          <div className="mb-2 flex items-center gap-2">
            <AlertTriangle className="h-3.5 w-3.5 text-ink" aria-hidden="true" />
            <Overline className="text-ink/60">Caveats</Overline>
          </div>
          <ul className="list-inside list-disc space-y-1 pl-1 text-sm text-ink-soft">
            {experiment.caveats.map((caveat, i) => (
              <li key={i} className="leading-relaxed">{caveat}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function MetricItem({
  icon: Icon,
  label,
}: {
  icon: React.ComponentType<{ className?: string }>
  label?: string
}) {
  if (!label) return null
  return (
    <div className="flex items-center gap-1.5 text-xs text-ink-soft">
      <Icon className="h-3.5 w-3.5 text-ink" aria-hidden="true" />
      <span className="break-all">{label}</span>
    </div>
  )
}
