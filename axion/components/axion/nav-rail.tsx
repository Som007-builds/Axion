'use client'

import { useEffect, useState } from 'react'
import Image from 'next/image'
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
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { getHealth } from '@/lib/api-client'
import { cn } from '@/lib/utils'

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
}

const navItems: NavItem[] = [
  { id: 'query', label: 'Research', icon: Search },
  { id: 'knowledge-graph', label: 'Knowledge Graph', icon: Network },
  { id: 'contradictions', label: 'Contradictions', icon: AlertTriangle },
  { id: 'gaps', label: 'Research Gaps', icon: Lightbulb },
  { id: 'timeline', label: 'Timeline', icon: Calendar },
  { id: 'evolution', label: 'Graph Evolution', icon: TrendingUp },
]

interface NavRailProps {
  activeView: AxionView
  onViewChange: (view: AxionView) => void
  onIngestionClick: () => void
}

export function NavRail({ activeView, onViewChange, onIngestionClick }: NavRailProps) {
  const [expanded, setExpanded] = useState(false)
  const [isDesktop, setIsDesktop] = useState(false)

  useEffect(() => {
    const media = window.matchMedia('(min-width: 768px)')
    const update = () => setIsDesktop(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

  const showExpanded = expanded && isDesktop

  // Real health signal.
  const { data: health, error: healthError } = useSWR('health', getHealth, {
    refreshInterval: 60000,
  })
  const online = !!health && !healthError

  return (
    <TooltipProvider delayDuration={0}>
      <nav
        aria-label="Primary"
        className={cn(
          'relative flex h-full w-[56px] shrink-0 flex-col border-r border-ink/25 bg-paper transition-all duration-200 ease-out',
          expanded && 'md:w-[200px]',
        )}
      >
        {/* Logo */}
        <div className="flex h-14 items-center justify-center border-b border-ink/25 px-3">
          <div className="flex items-center gap-2.5 overflow-hidden">
            <Image
              src="/axion-logo-mark.png"
              alt="AXION — Scientific Intelligence System"
              width={825}
              height={612}
              className="h-8 w-8 shrink-0 object-contain"
            />
            {showExpanded && (
              <span className="animate-fade-up whitespace-nowrap text-sm font-semibold tracking-[0.08em] text-ink">
                AXION
              </span>
            )}
          </div>
        </div>

        {/* Main Nav */}
        <div className="flex flex-1 flex-col gap-0.5 px-2 py-3">
          {navItems.map((item) => {
            const isActive = activeView === item.id
            const Icon = item.icon

            const button = (
              <button
                key={item.id}
                onClick={() => onViewChange(item.id)}
                aria-current={isActive ? 'page' : undefined}
                aria-label={item.label}
                className={cn(
                  'group relative flex w-full items-center gap-3 px-2.5 py-2 text-left text-[13px] transition-colors duration-150',
                  isActive
                    ? 'bg-ink/5 text-ink font-medium nav-active-rule'
                    : 'text-ink-soft hover:bg-ink/[0.03] hover:text-ink',
                )}
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                {showExpanded && (
                  <span className="min-w-0 truncate">{item.label}</span>
                )}
              </button>
            )

            if (!showExpanded) {
              return (
                <Tooltip key={item.id}>
                  <TooltipTrigger asChild>{button}</TooltipTrigger>
                  <TooltipContent side="right" sideOffset={8}>
                    <p className="text-xs">{item.label}</p>
                  </TooltipContent>
                </Tooltip>
              )
            }

            return button
          })}
        </div>

        {/* Bottom Section */}
        <div className="flex flex-col gap-0.5 border-t border-ink/25 px-2 py-3">
          {/* Ingestion */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={onIngestionClick}
                aria-label="Ingest papers"
                className="group flex w-full items-center gap-3 px-2.5 py-2 text-left text-[13px] text-ink-soft transition-colors duration-150 hover:bg-ink/[0.03] hover:text-ink focus-visible:outline-none"
              >
                <Database className="h-4 w-4 shrink-0" aria-hidden="true" />
                {showExpanded && <span className="whitespace-nowrap">Ingest Papers</span>}
              </button>
            </TooltipTrigger>
            {!showExpanded && (
              <TooltipContent side="right" sideOffset={8}>
                <p className="text-xs">Ingest Papers</p>
              </TooltipContent>
            )}
          </Tooltip>

          {/* System Health */}
          <Tooltip>
            <TooltipTrigger asChild>
              <div
                role="status"
                aria-label={online ? 'System online' : 'System offline'}
                className="flex w-full items-center gap-3 px-2.5 py-2 text-[13px] text-ink-soft"
              >
                {/* Monochrome health: solid square = online, outlined warning = offline */}
                {online ? (
                  <Activity className="h-4 w-4 shrink-0 text-ink" aria-hidden="true" />
                ) : (
                  <AlertTriangle
                    className="h-4 w-4 shrink-0 text-ink"
                    aria-hidden="true"
                  />
                )}
                {showExpanded && (
                  <span className="whitespace-nowrap">
                    {online ? 'System Online' : 'System Offline'}
                  </span>
                )}
              </div>
            </TooltipTrigger>
            {!showExpanded && (
              <TooltipContent side="right" sideOffset={8}>
                <p className="text-xs">
                  {online ? 'System Online' : 'System Offline'}
                </p>
              </TooltipContent>
            )}
          </Tooltip>

          {/* Collapse Toggle */}
          <button
            onClick={() => setExpanded(!expanded)}
            aria-expanded={expanded}
            aria-label={expanded ? 'Collapse navigation' : 'Expand navigation'}
            className="hidden w-full items-center justify-center py-1.5 text-ink-muted transition-colors duration-150 hover:text-ink focus-visible:outline-none md:flex"
          >
            {expanded ? (
              <PanelLeftClose className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <PanelLeftOpen className="h-3.5 w-3.5" aria-hidden="true" />
            )}
          </button>
        </div>
      </nav>
    </TooltipProvider>
  )
}
