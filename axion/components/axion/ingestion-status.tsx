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
import { Progress } from '@/components/ui/progress'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Overline, QrBlock } from '@/components/cg'
import {
  getIngestionStatus,
  triggerIngestion,
  runCustomIngestion,
  getIngestionProgress,
} from '@/lib/api-client'
import type { IngestionStatus as IngestionStatusType, CustomIngestionProgress } from '@/types/axion'

function formatDuration(seconds: number): string {
  if (seconds <= 0) return 'Calculating…'
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
  // After "Trigger New Ingestion" the previous run's completed snapshot is
  // still the latest server-side progress. Keep the form visible instead of
  // letting the progress sync immediately restore that old result.
  const [composingNew, setComposingNew] = useState(false)
  const [cronNotice, setCronNotice] = useState<string | null>(null)
  // A just-submitted custom run is `queued` until a worker claims it. Until
  // then the progress endpoint still returns the previous run's snapshot.
  const [pendingRun, setPendingRun] = useState<{
    topic: string
    previousLogCount: number
    startedAt: number
  } | null>(null)
  const lastProgressRef = useRef<CustomIngestionProgress | null>(null)

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

        if (pendingRun) {
          const isTerminal = !progress.running
          const isSameTopic = progress.topic === pendingRun.topic
          const logsGrew = progress.logs.length > pendingRun.previousLogCount
          const timedOut = Date.now() - pendingRun.startedAt > 60_000
          // Ignore the previous run's terminal snapshot while the new job is
          // still queued. Accept it once the new run reports progress, or
          // after a minute so a failed-to-start job cannot hide forever.
          if (isTerminal && !(isSameTopic && logsGrew) && !timedOut) {
            setPollingActive(true)
            return
          }
          setPendingRun(null)
        }

        lastProgressRef.current = progress
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

    // While the user is setting up a fresh run, do not rehydrate the last
    // completed snapshot — that would undo "Trigger New Ingestion".
    if (composingNew) {
      return
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
  }, [isOpen, pollingActive, customProgress?.running, composingNew, pendingRun])

  // Auto-scroll terminal log to bottom on updates; user scroll is not stolen
  // because scrollIntoView only runs when new log lines arrive.
  useEffect(() => {
    if (consoleEndRef.current) {
      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
      consoleEndRef.current.scrollIntoView({
        behavior: reduceMotion ? 'auto' : 'smooth',
      })
    }
  }, [customProgress?.logs])

  const handleStartCustomIngest = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!topic.trim() || isTriggering) return

    setIsTriggering(true)
    setTriggerError(null)

    try {
      await runCustomIngestion(topic.trim(), limit)
      setPendingRun({
        topic: topic.trim(),
        previousLogCount: lastProgressRef.current?.logs.length ?? 0,
        startedAt: Date.now(),
      })
      setComposingNew(false)
      setPollingActive(true)
      setCronNotice(null)
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
      setCronNotice(null)
      setPendingRun(null)
      setComposingNew(true)
    } catch (e) {
      console.error(e)
    }
  }

  const handleTriggerDefaultIngest = async () => {
    setIsTriggering(true)
    setTriggerError(null)
    setCronNotice(null)
    try {
      await triggerIngestion()
      setCronNotice('Background ingestion job queued.')
      mutateGeneral()
    } catch (err) {
      setTriggerError(
        err instanceof Error ? err.message : 'Failed to trigger the background ingestion job'
      )
    } finally {
      setIsTriggering(false)
    }
  }

  const isAnyIngestionRunning = generalStatus?.running || customProgress?.running || isTriggering

  function statusHeadline(progress: CustomIngestionProgress): string {
    switch (progress.status) {
      case 'queued':
        return 'Queued — waiting for a worker'
      case 'searching':
        return 'Searching ArXiv'
      case 'processing':
        return `Ingesting Paper ${progress.current_index}/${progress.limit}`
      case 'contradiction':
        return 'Checking Contradictions'
      case 'confidence':
        return 'Propagating Belief updates'
      case 'completed':
        return 'Completed'
      case 'failed':
        return 'Failed'
      default:
        return progress.status
    }
  }

  return (
    <Sheet open={isOpen} onOpenChange={handleOpenChange}>
      <SheetContent
        side="right"
        className="w-full border-l-[1.5px] border-ink/60 bg-paper text-ink sm:max-w-md"
      >
        <SheetHeader className="border-b border-ink/25 px-5 pt-8 pb-4">
          <SheetTitle className="flex items-center gap-3 text-lg font-semibold text-ink">
            <div className="flex h-7 w-7 items-center justify-center bg-ink text-paper">
              <Database className="h-4 w-4" aria-hidden="true" />
            </div>
            <span>Ingestion Pipeline</span>
            <QrBlock className="ml-auto mr-8" />
          </SheetTitle>
          <SheetDescription className="text-xs text-ink-soft">
            Feed new ArXiv publications into the multi-agent claims graph.
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 space-y-6 overflow-y-auto px-5 py-6">
          {/* Conditional Content */}
          {!customProgress || (customProgress.status === 'idle' && !customProgress.running) ? (
            /* Pipeline Form State */
            <form onSubmit={handleStartCustomIngest} className="space-y-5">
              <div className="space-y-2">
                <label
                  htmlFor="topic-input"
                  className="cg-overline block text-ink-muted"
                >
                  Research Field / Topic
                </label>
                <div className="relative">
                  <Search
                    className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted"
                    aria-hidden="true"
                  />
                  <Input
                    id="topic-input"
                    type="text"
                    required
                    placeholder="e.g., direct preference optimization"
                    value={topic}
                    onChange={(e) => setTopic(e.target.value)}
                    className="h-10 pl-9"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label
                  htmlFor="limit-input"
                  className="flex items-center justify-between"
                >
                  <span className="cg-overline block text-ink-muted">Target Papers Limit</span>
                  <span className="cg-mono-meta text-xs text-ink">{limit}</span>
                </label>
                <Input
                  id="limit-input"
                  type="number"
                  min={1}
                  max={20}
                  value={limit}
                  onChange={(e) => setLimit(parseInt(e.target.value) || 5)}
                  className="cg-mono-meta h-10"
                />
              </div>

              {triggerError && (
                <div
                  role="alert"
                  className="flex items-start gap-2 border border-ink bg-paper px-3 py-2.5 text-xs leading-relaxed text-ink"
                >
                  <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
                  <span>{triggerError}</span>
                </div>
              )}

              <Button
                type="submit"
                disabled={isTriggering || generalStatus?.running || !!pendingRun}
                className="h-10 w-full gap-2 bg-ink font-medium text-paper hover:bg-ink-soft"
              >
                <Play className="h-4 w-4" aria-hidden="true" />
                <span>
                  {pendingRun
                    ? 'Queued — waiting for a worker…'
                    : generalStatus?.running
                      ? 'Background Ingestion Running'
                      : isTriggering
                        ? 'Starting Pipeline…'
                        : 'Start Pipeline'}
                </span>
              </Button>
              {pendingRun && (
                <p role="status" className="text-[11px] leading-relaxed text-ink-muted">
                  Queued &ldquo;{pendingRun.topic}&rdquo;. The AI worker will start
                  this run shortly.
                </p>
              )}
              {generalStatus?.running && (
                <p className="text-[11px] leading-relaxed text-ink-muted">
                  Wait for the current background ingestion to finish before starting a
                  custom run.
                </p>
              )}

              <div className="space-y-2.5 border-t border-ink/25 pt-4">
                <p className="text-[11px] leading-relaxed text-ink-muted">
                  Alternatively, trigger a quick background incremental search on
                  pre-configured fields:
                </p>
                <Button
                  type="button"
                  onClick={handleTriggerDefaultIngest}
                  disabled={isAnyIngestionRunning}
                  variant="outline"
                  className="h-9 w-full gap-1.5 text-xs"
                >
                  <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>Trigger Cron Job Ingest</span>
                </Button>
                {cronNotice && (
                  <p role="status" className="text-[11px] leading-relaxed text-ink-muted">
                    {cronNotice}
                  </p>
                )}
              </div>
            </form>
          ) : (
            /* Pipeline Active or Completed/Failed State */
            <div className="animate-fade-up space-y-6">
              {/* Status Box */}
              <div className="space-y-4 border-[1.5px] border-ink/60 bg-paper p-4" aria-live="polite">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 space-y-1">
                    <span className="cg-mono-meta block truncate text-[10px] uppercase tracking-wide text-ink-muted">
                      TOPIC: &ldquo;{customProgress.topic}&rdquo;
                    </span>
                    <h3 className="text-sm font-semibold text-ink">
                      {statusHeadline(customProgress)}
                    </h3>
                  </div>

                  <span
                    className={`cg-mono-meta shrink-0 px-2.5 py-1 text-xs font-medium tabular-nums ${
                      customProgress.status === 'failed'
                        ? 'cg-hatch border border-ink text-ink'
                        : customProgress.status === 'completed'
                          ? 'bg-ink text-paper'
                          : 'border border-ink/60 text-ink'
                    }`}
                  >
                    {customProgress.percent}%
                  </span>
                </div>

                <Progress value={customProgress.percent} className="h-1.5" />

                {/* Dynamic Estimates */}
                {customProgress.running && (
                  <div className="flex items-center justify-between border-t border-ink/20 pt-3 text-xs">
                    <Overline className="text-ink-muted">Est. Remaining</Overline>
                    <span className="cg-mono-meta flex items-center gap-1.5 font-semibold text-ink">
                      <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                      {formatDuration(customProgress.remaining_seconds)}
                    </span>
                  </div>
                )}
              </div>

              {/* Pipeline Stats Summary */}
              <div className="grid grid-cols-3 border border-ink/30 bg-paper text-center">
                <div className="space-y-1 py-3">
                  <Overline className="block text-ink-muted">Papers</Overline>
                  <span className="cg-mono-meta inline-block text-sm font-semibold text-ink tabular-nums">
                    {customProgress.papers_added}
                  </span>
                </div>
                <div className="space-y-1 border-x border-ink/25 py-3">
                  <Overline className="block text-ink-muted">Claims</Overline>
                  <span className="cg-mono-meta inline-block text-sm font-semibold text-ink tabular-nums">
                    {customProgress.claims_added}
                  </span>
                </div>
                <div className="space-y-1 py-3">
                  <Overline className="block text-ink-muted">Conflicts</Overline>
                  <span className="cg-mono-meta inline-block text-sm font-semibold text-ink tabular-nums">
                    {customProgress.contradictions_found}
                  </span>
                </div>
              </div>

              {/* Active Paper Card */}
              {customProgress.current_paper_id && (
                <div className="space-y-2 border border-ink/40 bg-paper-secondary/60 p-4">
                  <span className="cg-mono-meta block text-[10px] font-medium uppercase tracking-wide text-ink">
                    ACTIVE: {customProgress.current_paper_id}
                  </span>
                  <p className="line-clamp-2 text-xs font-semibold leading-snug text-ink">
                    {customProgress.current_paper_title}
                  </p>
                  <div className="flex items-center gap-2 pt-1 text-[11px] text-ink-soft">
                    <span
                      aria-hidden="true"
                      className="animate-cg-blink inline-block h-1.5 w-1.5 bg-ink"
                    />
                    <span>{customProgress.current_step}</span>
                  </div>
                </div>
              )}

              {/* Live Console Logs */}
              <div className="space-y-2">
                <span className="flex items-center gap-1.5">
                  <Terminal className="h-3.5 w-3.5 text-ink" aria-hidden="true" />
                  <Overline className="text-ink-muted">Real-time Console</Overline>
                </span>
                <div className="h-60 space-y-1 overflow-y-auto border border-ink/30 bg-paper-secondary p-3 text-[11px] leading-normal text-ink-soft">
                  {customProgress.logs.map((log, idx) => (
                    <div
                      key={idx}
                      className="break-all whitespace-pre-wrap transition-colors hover:text-ink"
                    >
                      <span
                        aria-hidden="true"
                        className="cg-mono-meta mr-2 select-none text-ink-muted"
                      >
                        {String(idx + 1).padStart(3, '0')}
                      </span>
                      {log}
                    </div>
                  ))}
                  <div ref={consoleEndRef} />
                  {customProgress.running && (
                    <span
                      aria-hidden="true"
                      className="animate-cg-blink inline-block h-3 w-1.5 bg-ink align-middle"
                    />
                  )}
                </div>
                <span className="sr-only" aria-live="polite">
                  {customProgress.running
                    ? `Ingestion running: ${statusHeadline(customProgress)}`
                    : `Ingestion ${customProgress.status}. ${customProgress.error_message || ''}`}
                </span>
              </div>

              {/* Terminal Success/Failure block */}
              {!customProgress.running && (
                <div className="space-y-4">
                  {customProgress.status === 'completed' && (
                    <div className="flex items-start gap-3 border-[1.5px] border-ink bg-paper p-4">
                      <CheckCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-ink" aria-hidden="true" />
                      <div className="space-y-1">
                        <Overline className="text-ink">Ingestion Complete</Overline>
                        <p className="text-[11px] leading-relaxed text-ink-soft">
                          Knowledge graph migration, claim vectorization, and conflict
                          checks are complete.
                        </p>
                      </div>
                    </div>
                  )}
                  {customProgress.status === 'failed' && (
                    <div className="flex items-start gap-3 border-[1.5px] border-ink bg-paper p-4">
                      <AlertCircle
                        className="mt-0.5 h-4 w-4 flex-shrink-0 text-ink"
                        aria-hidden="true"
                      />
                      <div className="space-y-1">
                        <Overline className="text-ink">Ingestion Interrupted</Overline>
                        <p className="text-[11px] leading-relaxed text-ink-soft break-all">
                          {customProgress.error_message ||
                            'An error occurred during claims synthesis.'}
                        </p>
                      </div>
                    </div>
                  )}

                  <Button
                    onClick={handleResetProgressView}
                    variant="outline"
                    className="h-10 w-full gap-1.5 text-xs"
                  >
                    <span>Trigger New Ingestion</span>
                    <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
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
