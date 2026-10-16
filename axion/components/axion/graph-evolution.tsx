'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { TrendingUp, TrendingDown, RefreshCw, Loader2, BarChart3 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { getConfidenceDistribution, getMostChanged, recalculateConfidence } from '@/lib/api-client'
import type { ConfidenceDistribution, ChangedClaim } from '@/types/axion'

function ConfidenceBar({ 
  label, 
  count, 
  total, 
  gradient,
}: { 
  label: string
  count: number
  total: number
  gradient: string
}) {
  const percentage = total > 0 ? (count / total) * 100 : 0
  
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span className="text-[#94a3b8]">{label}</span>
        <span className="font-mono text-[#f0f6ff] tabular-nums">
          {count} <span className="text-[#475569]">({percentage.toFixed(1)}%)</span>
        </span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-[var(--axion-surface-3)]">
        <div
          className={`h-1.5 rounded-full ${gradient} transition-all duration-700 ease-out`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  )
}

function ChangedClaimCard({ claim }: { claim: ChangedClaim }) {
  const isPositive = claim.delta > 0
  
  return (
    <div className={`rounded-lg border border-[var(--axion-border-subtle)] bg-[var(--axion-surface-2)] p-4 space-y-2 axion-card-hover border-l-2 ${
      isPositive ? 'border-l-[#10b981]' : 'border-l-[#f43f5e]'
    }`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2">
          {isPositive ? (
            <TrendingUp className="h-4 w-4 text-[#10b981]" />
          ) : (
            <TrendingDown className="h-4 w-4 text-[#f43f5e]" />
          )}
          <span
            className={`font-mono text-sm font-semibold tabular-nums ${isPositive ? 'text-[#10b981]' : 'text-[#f43f5e]'}`}
          >
            {isPositive ? '+' : ''}{(claim.delta * 100).toFixed(1)}%
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-[#475569]">
          <span className="font-mono tabular-nums">{Math.round(claim.base_confidence * 100)}%</span>
          <span className="text-[#334155]">→</span>
          <span className="font-mono text-[#f0f6ff] tabular-nums">{Math.round(claim.current_confidence * 100)}%</span>
        </div>
      </div>
      <p className="text-sm text-[#94a3b8] line-clamp-2 leading-relaxed">{claim.claim_text}</p>
      <Badge
        variant="outline"
        className="border-[var(--axion-border-subtle)] bg-transparent text-[10px] text-[#475569]"
      >
        {claim.reason}
      </Badge>
    </div>
  )
}

export function GraphEvolution() {
  const [isRecalculating, setIsRecalculating] = useState(false)

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
    try {
      await recalculateConfidence()
      await Promise.all([mutateDistribution(), mutateClaims()])
    } catch (error) {
      console.error('Failed to recalculate:', error)
    } finally {
      setIsRecalculating(false)
    }
  }

  const isLoading = distLoading || claimsLoading
  const hasError = distError || claimsError

  return (
    <div className="space-y-6 animate-fade-up">
      {/* Header with recalculate button */}
      <div className="flex items-center justify-between">
        <div />
        <Button
          onClick={handleRecalculate}
          disabled={isRecalculating}
          variant="outline"
          size="sm"
          className="border-[var(--axion-border-subtle)] bg-transparent text-[#94a3b8] hover:border-[#3b82f6]/30 hover:text-[#f0f6ff] hover:bg-[rgba(59,130,246,0.04)] transition-all duration-150"
        >
          {isRecalculating ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          <span>Recalculate</span>
        </Button>
      </div>

      {/* Error state */}
      {hasError && (
        <div className="rounded-xl border border-[#f43f5e]/20 bg-[#f43f5e]/5 p-4">
          <p className="text-sm text-[#f43f5e]">
            Failed to load confidence data. Is the API running?
          </p>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Confidence Distribution */}
        <div className="rounded-xl border border-[var(--axion-border-subtle)] axion-surface axion-inner-glow p-5 space-y-6">
          <div className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-[#3b82f6]" />
            <h4 className="font-medium text-[#f0f6ff]">Confidence Distribution</h4>
          </div>

          {isLoading ? (
            <div className="space-y-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="space-y-2">
                  <div className="animate-shimmer h-4 w-full rounded" />
                  <div className="animate-shimmer h-1.5 w-full rounded" />
                </div>
              ))}
            </div>
          ) : distribution ? (
            <>
              <div className="space-y-4">
                <ConfidenceBar
                  label="High (>80%)"
                  count={distribution.high}
                  total={distribution.total}
                  gradient="bg-gradient-to-r from-[#10b981] to-[#06b6d4]"
                />
                <ConfidenceBar
                  label="Medium (50-80%)"
                  count={distribution.medium}
                  total={distribution.total}
                  gradient="bg-gradient-to-r from-[#f59e0b] to-[#f97316]"
                />
                <ConfidenceBar
                  label="Low (<50%)"
                  count={distribution.low}
                  total={distribution.total}
                  gradient="bg-gradient-to-r from-[#f43f5e] to-[#e11d48]"
                />
              </div>

              <div className="space-y-2 border-t border-[var(--axion-border-subtle)] pt-4">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-[#475569]">Total claims</span>
                  <span className="font-mono text-[#f0f6ff] tabular-nums">{distribution.total}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-[#475569]">Average confidence</span>
                  <span className="font-mono text-[#f0f6ff] tabular-nums">
                    {Math.round(distribution.average * 100)}%
                  </span>
                </div>
              </div>
            </>
          ) : null}
        </div>

        {/* Most Changed Claims */}
        <div className="rounded-xl border border-[var(--axion-border-subtle)] axion-surface axion-inner-glow p-5 space-y-4">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-[#10b981]" />
            <h4 className="font-medium text-[#f0f6ff]">Most Changed Claims</h4>
          </div>

          {isLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="animate-shimmer h-20 w-full rounded-lg" />
              ))}
            </div>
          ) : changedClaims && changedClaims.length > 0 ? (
            <div className="space-y-3 max-h-[400px] overflow-y-auto stagger-children">
              {changedClaims.map((claim) => (
                <ChangedClaimCard key={claim.claim_id} claim={claim} />
              ))}
            </div>
          ) : (
            <div className="py-8 text-center">
              <TrendingUp className="mx-auto h-8 w-8 text-[#334155]" />
              <p className="mt-3 text-sm text-[#94a3b8]">
                No significant confidence changes detected
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
