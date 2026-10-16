'use client'

import { useState, useEffect, useRef } from 'react'
import useSWR from 'swr'
import {
  RefreshCw,
  Clock,
  Play,
  CheckCircle,
  AlertCircle,
  Terminal,
  ArrowRight,
  Database,
  Search,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import {
  getIngestionStatus,
  triggerIngestion,
  runCustomIngestion,
  getIngestionProgress,
} from '@/lib/api-client'
import type { IngestionStatus as IngestionStatusType, CustomIngestionProgress } from '@/types/axion'

function formatDuration(seconds: number): string {
  if (seconds <= 0) return 'Calculating...'
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  if (mins > 0) {
    return `${mins}m ${secs}s`
  }
  return `${secs}s`
}

interface IngestionStatusProps {
  externalOpen?: boolean
  onExternalClose?: () => void
}

export function IngestionStatus({ externalOpen, onExternalClose }: IngestionStatusProps) {
  // The sheet is driven by the parent's `externalOpen` when provided; otherwise
  // it manages its own open state. Deriving avoids syncing a prop into state.
  const [internalOpen, setInternalOpen] = useState(false)
  const isOpen = externalOpen ?? internalOpen
  const [topic, setTopic] = useState('')
  const [limit, setLimit] = useState(5)
  const [customProgress, setCustomProgress] = useState<CustomIngestionProgress | null>(null)
  const [isTriggering, setIsTriggering] = useState(false)
  const [pollingActive, setPollingActive] = useState(false)
  const [triggerError, setTriggerError] = useState<string | null>(null)

  const consoleEndRef = useRef<HTMLDivElement | null>(null)

  const handleOpenChange = (open: boolean) => {
    setInternalOpen(open)
    if (!open && onExternalClose) {
      onExternalClose()
    }
  }

  // Fetch general background cron ingestion status
  const { data: generalStatus, mutate: mutateGeneral } = useSWR<IngestionStatusType>(
    'ingestion-status',
    getIngestionStatus,
    {
      refreshInterval: 30000,
    }
  )

  // Sync / poll custom progress when sheet is open or polling is active
  useEffect(() => {
    let intervalId: NodeJS.Timeout | null = null

    const fetchProgress = async () => {
      try {
        const progress = await getIngestionProgress()
        setCustomProgress(progress)
        
        if (progress.running) {
          setPollingActive(true)
        } else {
          setPollingActive(false)
        }
      } catch (err) {
        console.error('Error fetching custom ingestion progress:', err)
      }
    }

    // Run once immediately on sheet open or poll toggle
    if (isOpen || pollingActive) {
      fetchProgress()
    }

    // Set up polling interval if active
    if (pollingActive || (isOpen && customProgress?.running)) {
      intervalId = setInterval(fetchProgress, 2000)
    }

    return () => {
      if (intervalId) clearInterval(intervalId)
    }
  }, [isOpen, pollingActive, customProgress?.running])

  // Auto-scroll terminal log to bottom on updates
  useEffect(() => {
    if (consoleEndRef.current) {
      consoleEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [customProgress?.logs])

  const handleStartCustomIngest = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!topic.trim() || isTriggering) return

    setIsTriggering(true)
    setTriggerError(null)

    try {
      await runCustomIngestion(topic.trim(), limit)
      setPollingActive(true)
      mutateGeneral()
    } catch (err) {
      setTriggerError(err instanceof Error ? err.message : 'Failed to start ingestion pipeline')
    } finally {
      setIsTriggering(false)
    }
  }

  const handleResetProgressView = async () => {
    try {
      mutateGeneral()
      setTopic('')
      setLimit(5)
      setCustomProgress(null)
      setPollingActive(false)
      setTriggerError(null)
    } catch (e) {
      console.error(e)
    }
  }

  const handleTriggerDefaultIngest = async () => {
    setIsTriggering(true)
    try {
      await triggerIngestion()
      mutateGeneral()
    } catch (err) {
      console.error('Failed to trigger default cron:', err)
    } finally {
      setIsTriggering(false)
    }
  }

  const isAnyIngestionRunning = generalStatus?.running || customProgress?.running || isTriggering

  return (
    <Sheet open={isOpen} onOpenChange={handleOpenChange}>
      <SheetContent
        side="right"
        className="border-l border-[var(--axion-border-subtle)] bg-[var(--axion-surface-1)] text-[#f0f6ff] w-full sm:max-w-md flex flex-col h-full overflow-hidden"
      >
        <SheetHeader className="pb-4 border-b border-[var(--axion-border-subtle)]">
          <SheetTitle className="text-[#f0f6ff] text-lg flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-[#3b82f6]/20 to-[#06b6d4]/20">
              <Database className="h-4 w-4 text-[#3b82f6]" />
            </div>
            <span>Ingestion Pipeline</span>
          </SheetTitle>
          <SheetDescription className="text-[#475569] text-xs">
            Feed new ArXiv publications into the multi-agent claims graph.
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto py-6 space-y-6">
          {/* Conditional Content */}
          {!customProgress || (customProgress.status === 'idle' && !customProgress.running) ? (
            /* Pipeline Form State */
            <form onSubmit={handleStartCustomIngest} className="space-y-5">
              <div className="space-y-2">
                <Label htmlFor="topic-input" className="text-[#94a3b8] text-xs">
                  Research Field / Topic
                </Label>
                <div className="relative">
                  <Search className="absolute left-3 top-2.5 h-4 w-4 text-[#334155]" />
                  <Input
                    id="topic-input"
                    type="text"
                    required
                    placeholder="e.g., direct preference optimization"
                    value={topic}
                    onChange={(e) => setTopic(e.target.value)}
                    className="pl-9 border-[var(--axion-border-subtle)] bg-[var(--axion-surface-2)] text-[#f0f6ff] placeholder:text-[#334155] focus-visible:border-[#3b82f6] focus-visible:ring-1 focus-visible:ring-[#3b82f6]/50"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="limit-input" className="text-[#94a3b8] text-xs flex justify-between">
                  <span>Target Papers Limit</span>
                  <span className="text-[#475569] font-mono">{limit}</span>
                </Label>
                <Input
                  id="limit-input"
                  type="number"
                  min={1}
                  max={20}
                  value={limit}
                  onChange={(e) => setLimit(parseInt(e.target.value) || 5)}
                  className="border-[var(--axion-border-subtle)] bg-[var(--axion-surface-2)] text-[#f0f6ff] focus-visible:border-[#3b82f6] focus-visible:ring-1 focus-visible:ring-[#3b82f6]/50"
                />
              </div>

              {triggerError && (
                <div className="flex items-center gap-2 text-xs text-[#f43f5e] bg-[#f43f5e]/5 border border-[#f43f5e]/20 p-3 rounded-lg">
                  <AlertCircle className="h-4 w-4 flex-shrink-0" />
                  <span>{triggerError}</span>
                </div>
              )}

              <Button
                type="submit"
                disabled={isTriggering}
                className="w-full border border-[#10b981]/40 bg-[#10b981]/5 text-[#10b981] hover:bg-[#10b981]/10 transition-all flex items-center justify-center gap-2 h-10 font-medium"
              >
                <Play className="h-4 w-4" />
                <span>{isTriggering ? 'Starting Pipeline...' : 'Start Pipeline'}</span>
              </Button>

              <div className="pt-4 border-t border-[var(--axion-border-subtle)] space-y-3">
                <p className="text-[11px] text-[#334155] leading-relaxed">
                  Alternatively, trigger a quick background incremental search on pre-configured fields:
                </p>
                <Button
                  type="button"
                  onClick={handleTriggerDefaultIngest}
                  disabled={isAnyIngestionRunning}
                  className="w-full border border-[var(--axion-border-subtle)] bg-transparent text-[#94a3b8] hover:text-[#f0f6ff] hover:bg-[rgba(59,130,246,0.04)] transition-all text-xs flex items-center justify-center gap-1.5 h-9"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  <span>Trigger Cron Job Ingest</span>
                </Button>
              </div>
            </form>
          ) : (
            /* Pipeline Active or Completed/Failed State */
            <div className="space-y-6">
              {/* Status Box */}
              <div className="rounded-xl border border-[var(--axion-border-subtle)] axion-surface p-4 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    <span className="text-[10px] text-[#475569] uppercase tracking-wider block">
                      Topic: &ldquo;{customProgress.topic}&rdquo;
                    </span>
                    <h4 className="font-semibold text-sm capitalize text-[#f0f6ff]">
                      {customProgress.status === 'processing'
                        ? `Ingesting Paper ${customProgress.current_index}/${customProgress.limit}`
                        : customProgress.status === 'contradiction'
                        ? 'Checking Contradictions'
                        : customProgress.status === 'confidence'
                        ? 'Propagating Belief updates'
                        : customProgress.status}
                    </h4>
                  </div>

                  <span
                    className={`text-xs px-2.5 py-1 rounded-full font-mono ${
                      customProgress.status === 'completed'
                        ? 'bg-[#10b981]/10 text-[#10b981]'
                        : customProgress.status === 'failed'
                        ? 'bg-[#f43f5e]/10 text-[#f43f5e]'
                        : 'bg-[#3b82f6]/10 text-[#3b82f6]'
                    }`}
                  >
                    {customProgress.percent}%
                  </span>
                </div>

                <Progress value={customProgress.percent} className="h-1.5 bg-[var(--axion-surface-3)]" />

                {/* Dynamic Estimates */}
                {customProgress.running && (
                  <div className="flex items-center justify-between border-t border-[var(--axion-border-subtle)] pt-3 text-xs">
                    <span className="text-[#475569]">Estimated Time Remaining:</span>
                    <span className="font-mono text-[#f0f6ff] font-semibold flex items-center gap-1">
                      <Clock className="h-3.5 w-3.5 text-[#3b82f6]" />
                      {formatDuration(customProgress.remaining_seconds)}
                    </span>
                  </div>
                )}
              </div>

              {/* Pipeline Stats Summary */}
              <div className="grid grid-cols-3 gap-3 border border-[var(--axion-border-subtle)] rounded-xl p-3 bg-[var(--axion-surface-1)] text-center">
                <div className="space-y-1">
                  <span className="text-[10px] text-[#475569] block">Papers</span>
                  <span className="font-semibold text-sm text-[#f0f6ff] tabular-nums">
                    {customProgress.papers_added}
                  </span>
                </div>
                <div className="space-y-1 border-x border-[var(--axion-border-subtle)]">
                  <span className="text-[10px] text-[#475569] block">Claims</span>
                  <span className="font-semibold text-sm text-[#f0f6ff] tabular-nums">
                    {customProgress.claims_added}
                  </span>
                </div>
                <div className="space-y-1">
                  <span className="text-[10px] text-[#475569] block">Conflicts</span>
                  <span className="font-semibold text-sm text-[#f0f6ff] tabular-nums">
                    {customProgress.contradictions_found}
                  </span>
                </div>
              </div>

              {/* Active Paper Card */}
              {customProgress.current_paper_id && (
                <div className="rounded-xl border border-[#3b82f6]/15 bg-[#3b82f6]/[0.02] p-4 space-y-2">
                  <span className="text-[10px] font-medium text-[#3b82f6] uppercase tracking-wider block">
                    Active: {customProgress.current_paper_id}
                  </span>
                  <p className="text-xs font-semibold text-[#f0f6ff] leading-snug line-clamp-2">
                    {customProgress.current_paper_title}
                  </p>
                  <div className="flex items-center gap-2 text-[11px] text-[#475569] pt-1">
                    <span className="animate-status-pulse inline-block h-1.5 w-1.5 rounded-full bg-[#3b82f6]" />
                    <span>{customProgress.current_step}</span>
                  </div>
                </div>
              )}

              {/* Live Console Logs */}
              <div className="space-y-2">
                <Label className="text-[#94a3b8] text-xs flex items-center gap-1.5">
                  <Terminal className="h-4 w-4 text-[#8b5cf6]" />
                  <span>Real-time Console</span>
                </Label>
                <div className="bg-[#020408] border border-[var(--axion-border-subtle)] rounded-xl p-3 font-mono text-[10px] text-[#475569] h-60 overflow-y-auto space-y-1.5">
                  {customProgress.logs.map((log, idx) => (
                    <div key={idx} className="whitespace-pre-wrap leading-normal font-mono break-all hover:text-[#94a3b8] transition-colors">
                      <span className="text-[#334155] mr-2 select-none">{String(idx + 1).padStart(3, '0')}</span>
                      {log}
                    </div>
                  ))}
                  <div ref={consoleEndRef} />
                  {customProgress.running && (
                    <div className="animate-pulse inline-block w-1.5 h-3 bg-[#3b82f6] align-middle" />
                  )}
                </div>
              </div>

              {/* Terminal Success/Failure block */}
              {!customProgress.running && (
                <div className="space-y-4">
                  {customProgress.status === 'completed' && (
                    <div className="rounded-xl border border-[#10b981]/20 bg-[#10b981]/5 p-4 flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-[#10b981] flex-shrink-0 mt-0.5" />
                      <div className="space-y-1">
                        <h5 className="font-semibold text-xs text-[#10b981]">Ingestion Complete</h5>
                        <p className="text-[11px] text-[#94a3b8] leading-relaxed">
                          Knowledge graph migration, claim vectorization, and conflict checks are complete.
                        </p>
                      </div>
                    </div>
                  )}
                  {customProgress.status === 'failed' && (
                    <div className="rounded-xl border border-[#f43f5e]/20 bg-[#f43f5e]/5 p-4 flex items-start gap-3">
                      <AlertCircle className="h-5 w-5 text-[#f43f5e] flex-shrink-0 mt-0.5" />
                      <div className="space-y-1">
                        <h5 className="font-semibold text-xs text-[#f43f5e]">Ingestion Interrupted</h5>
                        <p className="text-[11px] text-[#94a3b8] leading-relaxed">
                          {customProgress.error_message || 'An error occurred during claims synthesis.'}
                        </p>
                      </div>
                    </div>
                  )}

                  <Button
                    onClick={handleResetProgressView}
                    className="w-full border border-[var(--axion-border-subtle)] bg-transparent text-[#94a3b8] hover:text-[#f0f6ff] hover:bg-[rgba(59,130,246,0.04)] transition-all text-xs flex items-center justify-center gap-1.5 h-10"
                  >
                    <span>Trigger New Ingestion</span>
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
