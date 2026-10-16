'use client'

import useSWR from 'swr'
import { FileText, MessageSquare, AlertTriangle, Lightbulb, FlaskConical } from 'lucide-react'
import { getStats } from '@/lib/api-client'
import { Skeleton } from '@/components/ui/skeleton'
import type { GraphStats } from '@/types/axion'

const statItems = [
  {
    key: 'papers' as const,
    label: 'Papers',
    icon: FileText,
    color: 'text-[#f0f6ff]',
  },
  {
    key: 'claims' as const,
    label: 'Claims',
    icon: MessageSquare,
    color: 'text-[#8b5cf6]',
  },
  {
    key: 'contradictions' as const,
    label: 'Contradictions',
    icon: AlertTriangle,
    color: 'text-[#f43f5e]',
  },
  {
    key: 'gaps' as const,
    label: 'Gaps',
    icon: Lightbulb,
    color: 'text-[#8b5cf6]',
  },
  {
    key: 'experiments' as const,
    label: 'Experiments',
    icon: FlaskConical,
    color: 'text-[#10b981]',
  },
]

export function DashboardStats() {
  const { data, isLoading, error } = useSWR<GraphStats>('stats', getStats, {
    refreshInterval: 60000,
  })

  if (error) {
    return (
      <div className="flex items-center gap-2 text-xs text-[#f43f5e]">
        <AlertTriangle className="h-3 w-3" />
        <span>API offline</span>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-3 stagger-children">
      {statItems.map((item) => {
        const Icon = item.icon
        return (
          <div
            key={item.key}
            className="flex items-center gap-2 rounded-lg border border-[var(--axion-border-subtle)] bg-[var(--axion-surface-1)] px-3 py-1.5 axion-card-hover"
          >
            <Icon className={`h-3.5 w-3.5 ${item.color}`} />
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-[#475569]">{item.label}</span>
              {isLoading ? (
                <Skeleton className="h-4 w-8 animate-shimmer" />
              ) : (
                <span className="font-mono text-sm font-semibold text-[#f0f6ff] tabular-nums">
                  {data?.[item.key]?.toLocaleString() ?? '—'}
                </span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
