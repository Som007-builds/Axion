'use client'

import useSWR from 'swr'
import { FileText, MessageSquare, AlertTriangle, Lightbulb, FlaskConical, XCircle } from 'lucide-react'
import { getStats } from '@/lib/api-client'
import { Skeleton } from '@/components/ui/skeleton'
import type { GraphStats } from '@/types/axion'

const statItems = [
  {
    key: 'papers' as const,
    label: 'Papers',
    icon: FileText,
  },
  {
    key: 'claims' as const,
    label: 'Claims',
    icon: MessageSquare,
  },
  {
    key: 'contradictions' as const,
    label: 'Contradictions',
    icon: AlertTriangle,
  },
  {
    key: 'gaps' as const,
    label: 'Gaps',
    icon: Lightbulb,
  },
  {
    key: 'experiments' as const,
    label: 'Experiments',
    icon: FlaskConical,
  },
]

export function DashboardStats() {
  const { data, isLoading, error } = useSWR<GraphStats>('stats', getStats, {
    refreshInterval: 60000,
  })

  if (error) {
    return (
      <div className="flex items-center gap-2 text-xs text-ink">
        <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="cg-mono-meta text-[11px]">STATUS: API OFFLINE</span>
      </div>
    )
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {statItems.map((item) => {
        const Icon = item.icon
        return (
          <div
            key={item.key}
            className="flex items-center gap-2 border border-ink/25 bg-paper px-2.5 py-1.5 transition-colors duration-150 hover:border-ink/60"
          >
            <Icon className="h-3.5 w-3.5 text-ink" aria-hidden="true" />
            <span className="cg-overline text-ink-muted">{item.label}</span>
            {isLoading ? (
              <Skeleton className="h-3.5 w-8" />
            ) : (
              <span className="cg-mono-meta text-[13px] font-medium text-ink tabular-nums">
                {data?.[item.key]?.toLocaleString() ?? '—'}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}
