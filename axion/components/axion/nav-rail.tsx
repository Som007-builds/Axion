'use client'

import { useState } from 'react'
import useSWR from 'swr'
import {
  Search,
  Network,
  AlertTriangle,
  Lightbulb,
  Calendar,
  TrendingUp,
  Database,
  Activity,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { getHealth } from '@/lib/api-client'

export type AxionView =
  | 'query'
  | 'knowledge-graph'
  | 'contradictions'
  | 'gaps'
  | 'timeline'
  | 'evolution'

interface NavItem {
  id: AxionView
  label: string
  icon: React.ComponentType<{ className?: string }>
  shortcut?: string
}

const navItems: NavItem[] = [
  { id: 'query', label: 'Research', icon: Search, shortcut: '1' },
  { id: 'knowledge-graph', label: 'Knowledge Graph', icon: Network, shortcut: '2' },
  { id: 'contradictions', label: 'Contradictions', icon: AlertTriangle, shortcut: '3' },
  { id: 'gaps', label: 'Research Gaps', icon: Lightbulb, shortcut: '4' },
  { id: 'timeline', label: 'Timeline', icon: Calendar, shortcut: '5' },
  { id: 'evolution', label: 'Graph Evolution', icon: TrendingUp, shortcut: '6' },
]

interface NavRailProps {
  activeView: AxionView
  onViewChange: (view: AxionView) => void
  onIngestionClick: () => void
}

export function NavRail({ activeView, onViewChange, onIngestionClick }: NavRailProps) {
  const [expanded, setExpanded] = useState(false)

  // Real health signal instead of a hardcoded "System Online" indicator.
  const { data: health, error: healthError } = useSWR('health', getHealth, {
    refreshInterval: 60000,
  })
  const online = !!health && !healthError
  const healthColor = online ? '#10b981' : '#f43f5e'
  const healthLabel = online ? 'System Online' : 'System Offline'

  return (
    <TooltipProvider delayDuration={0}>
      <nav
        className={`
          relative flex h-full flex-col border-r border-[var(--axion-border-subtle)]
          bg-[var(--axion-surface-1)] transition-all duration-200 ease-out
          ${expanded ? 'w-[200px]' : 'w-[56px]'}
        `}
      >
        {/* Logo */}
        <div className="flex h-14 items-center justify-center border-b border-[var(--axion-border-subtle)] px-3">
          <div className="flex items-center gap-2.5 overflow-hidden">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-[#3b82f6] to-[#06b6d4]">
              <span className="font-mono text-xs font-bold text-white">A</span>
            </div>
            {expanded && (
              <span className="whitespace-nowrap text-sm font-semibold text-[#f0f6ff] animate-fade-up">
                AXION
              </span>
            )}
          </div>
        </div>

        {/* Main Nav */}
        <div className="flex flex-1 flex-col gap-1 px-2 py-3">
          {navItems.map((item) => {
            const isActive = activeView === item.id
            const Icon = item.icon

            const button = (
              <button
                key={item.id}
                onClick={() => onViewChange(item.id)}
                className={`
                  group relative flex w-full items-center gap-3 rounded-lg px-2.5 py-2
                  text-sm transition-all duration-150 ease-out
                  ${isActive
                    ? 'bg-[rgba(59,130,246,0.08)] text-[#f0f6ff] nav-active-indicator'
                    : 'text-[#475569] hover:bg-[rgba(59,130,246,0.04)] hover:text-[#94a3b8]'
                  }
                `}
              >
                <Icon className={`h-4 w-4 shrink-0 transition-colors duration-150 ${
                  isActive ? 'text-[#3b82f6]' : 'text-[#475569] group-hover:text-[#94a3b8]'
                }`} />
                {expanded && (
                  <span className="whitespace-nowrap truncate">{item.label}</span>
                )}
                {expanded && item.shortcut && (
                  <span className="ml-auto font-mono text-[10px] text-[#334155]">{item.shortcut}</span>
                )}
              </button>
            )

            if (!expanded) {
              return (
                <Tooltip key={item.id}>
                  <TooltipTrigger asChild>{button}</TooltipTrigger>
                  <TooltipContent side="right" sideOffset={8} className="bg-[#0f1318] border-[var(--axion-border-subtle)] text-[#f0f6ff]">
                    <p className="text-xs">{item.label}</p>
                  </TooltipContent>
                </Tooltip>
              )
            }

            return button
          })}
        </div>

        {/* Bottom Section */}
        <div className="flex flex-col gap-1 border-t border-[var(--axion-border-subtle)] px-2 py-3">
          {/* Ingestion */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={onIngestionClick}
                className="group flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-sm text-[#475569] transition-all duration-150 hover:bg-[rgba(59,130,246,0.04)] hover:text-[#94a3b8]"
              >
                <Database className="h-4 w-4 shrink-0 text-[#475569] group-hover:text-[#94a3b8]" />
                {expanded && <span className="whitespace-nowrap">Ingest Papers</span>}
              </button>
            </TooltipTrigger>
            {!expanded && (
              <TooltipContent side="right" sideOffset={8} className="bg-[#0f1318] border-[var(--axion-border-subtle)] text-[#f0f6ff]">
                <p className="text-xs">Ingest Papers</p>
              </TooltipContent>
            )}
          </Tooltip>

          {/* System Health */}
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="group flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-sm text-[#475569]">
                <Activity className="h-4 w-4 shrink-0" style={{ color: healthColor }} />
                {expanded && <span className="whitespace-nowrap text-[#475569]">{healthLabel}</span>}
              </div>
            </TooltipTrigger>
            {!expanded && (
              <TooltipContent side="right" sideOffset={8} className="bg-[#0f1318] border-[var(--axion-border-subtle)] text-[#f0f6ff]">
                <p className="text-xs">{healthLabel}</p>
              </TooltipContent>
            )}
          </Tooltip>

          {/* Collapse Toggle */}
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex w-full items-center justify-center rounded-lg py-1.5 text-[#334155] transition-colors duration-150 hover:text-[#94a3b8]"
          >
            {expanded ? <ChevronLeft className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          </button>
        </div>
      </nav>
    </TooltipProvider>
  )
}
