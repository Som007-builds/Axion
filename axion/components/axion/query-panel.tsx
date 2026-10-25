'use client'

import * as React from 'react'
import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Search,
  ChevronDown,
  ChevronRight,
  Loader2,
  BookOpen,
  Brain,
  Swords,
  HelpCircle,
  FlaskConical,
  ExternalLink,
  Sparkles,
  Plus,
  Trash2,
  History,
  MessageSquare,
  ShieldAlert,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { runQuery } from '@/lib/api-client'
import type { CoordinatorOutput, JobStatus, ReflectionStep } from '@/types/axion'
import ReactMarkdown from 'react-markdown'
import { useIsClient } from '@/lib/use-is-client'
import { cn } from '@/lib/utils'
import {
  Overline,
  ErrorBanner,
  PixelGlitch,
  QrBlock,
} from '@/components/cg'

// ─── Raw report JSON type from the coordinator ──────────────────────────────

interface RawReport {
  summary?: string
  consensus?: { finding: string; citations?: string[] }[]
  disputed?: {
    topic: string
    position_a: { claim: string; paper: string } | string
    position_b: { claim: string; paper: string } | string
  }[]
  missing?: string[]
  recommended_experiments?: string[]
  confidence_in_answer?: string
  confidence_reason?: string
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const MAX_HISTORY = 20

function parseRaw(rawStr: string): RawReport {
  try {
    const parsed = JSON.parse(rawStr)
    return parsed && typeof parsed === 'object' ? (parsed as RawReport) : {}
  } catch {
    return {}
  }
}

function safeStorageGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function safeStorageSet(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // Local storage may be unavailable (private mode/quota). History remains
    // usable for this session only.
  }
}

function finiteNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function normalizeOutput(value: unknown): CoordinatorOutput | null {
  if (!value || typeof value !== 'object') return null
  const output = value as Partial<CoordinatorOutput>
  const rawValue = output.raw
  const raw =
    typeof rawValue === 'string'
      ? rawValue
      : rawValue && typeof rawValue === 'object'
        ? JSON.stringify(rawValue)
        : '{}'

  return {
    report: typeof output.report === 'string' ? output.report : '',
    raw,
    iterations: finiteNumber(output.iterations) ?? 1,
    plan: Array.isArray(output.plan)
      ? output.plan.filter((step): step is string => typeof step === 'string')
      : [],
    reflection_log: Array.isArray(output.reflection_log)
      ? output.reflection_log.filter(
          (step): step is ReflectionStep =>
            Boolean(step) && typeof step === 'object' && typeof step.observation === 'string',
        )
      : [],
    confidence: finiteNumber(output.confidence) ?? 0,
    confidence_label: output.confidence_label,
    sources: Array.isArray(output.sources)
      ? output.sources.filter(
          (source): source is string =>
            typeof source === 'string' && source.trim() !== '' && source.trim() !== '?',
        )
      : [],
    source_count: finiteNumber(output.source_count),
    claim_count: finiteNumber(output.claim_count),
    contradiction_count: finiteNumber(output.contradiction_count),
    gap_count: finiteNumber(output.gap_count),
  }
}

function makeHistoryId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function normalizeHistory(value: unknown): QueryHistoryItem[] {
  if (!Array.isArray(value)) return []
  const items: QueryHistoryItem[] = []
  for (const rawItem of value) {
    if (!rawItem || typeof rawItem !== 'object') continue
    const item = rawItem as Partial<QueryHistoryItem>
    if (typeof item.question !== 'string' || !item.question.trim()) continue
    const result = normalizeOutput(item.result)
    if (!result) continue
    items.push({
      id: typeof item.id === 'string' && item.id ? item.id : makeHistoryId(),
      question: item.question,
      timestamp:
        typeof item.timestamp === 'string' && item.timestamp
          ? item.timestamp
          : 'Earlier query',
      result,
    })
  }
  return items.slice(0, MAX_HISTORY)
}

function deriveReportTitle(question: string): string {
  let title = question.replace(/\s+/g, ' ').trim().replace(/[?!.]+$/, '')
  title = title.replace(
    /^(what|how|why|when|where|which|who)\s+(is|are|was|were|does|do|did|has|have|can|could|should|would)\b\s*/i,
    '',
  )
  title = title.replace(/^(can|could|should|would|do|does|did|is|are)\b\s*/i, '')
  if (!title) return question.trim()
  title = title.charAt(0).toUpperCase() + title.slice(1)
  if (title.length <= 96) return title
  const clipped = title.slice(0, 93)
  const lastSpace = clipped.lastIndexOf(' ')
  return `${clipped.slice(0, lastSpace > 60 ? lastSpace : 93).trimEnd()}…`
}

function modelConfidence(raw: RawReport): {
  label: 'HIGH' | 'MEDIUM' | 'LOW' | 'NOT REPORTED'
  reported: boolean
} {
  const value = raw.confidence_in_answer?.trim().toLowerCase()
  if (value === 'high' || value === 'medium' || value === 'low') {
    return { label: value.toUpperCase() as 'HIGH' | 'MEDIUM' | 'LOW', reported: true }
  }
  return { label: 'NOT REPORTED', reported: false }
}

function arxivUrl(id: string): string {
  const clean = id.replace(/[\[\]]/g, '').trim()
  return `https://arxiv.org/abs/${clean}`
}

// ─── Citation chip ───────────────────────────────────────────────────────────

function CitationChip({ id }: { id: string }) {
  const clean = id.replace(/[\[\]]/g, '').trim()
  return (
    <a
      href={arxivUrl(clean)}
      target="_blank"
      rel="noopener noreferrer"
      className="cg-mono-meta inline-flex items-center gap-1 border border-ink/40 bg-ink/[0.04] px-1.5 py-0.5 text-[11px] text-ink transition-colors duration-150 hover:bg-ink hover:text-paper focus-visible:outline-none"
    >
      {clean}
      <ExternalLink className="h-2.5 w-2.5" aria-hidden="true" />
    </a>
  )
}

// ─── Collapsible sections: execution plan / reasoning trace ─────────────────

function CollapsibleSection({
  label,
  icon,
  children,
}: {
  label: string
  icon: React.ReactNode
  children: React.ReactNode
}) {
  const [isOpen, setIsOpen] = useState(false)
  if (React.Children.count(children) === 0) return null

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger className="flex w-full items-center gap-2 py-1.5 text-left text-sm text-ink-soft transition-colors hover:text-ink focus-visible:outline-none">
        {isOpen ? (
          <ChevronDown className="h-4 w-4 shrink-0" aria-hidden="true" />
        ) : (
          <ChevronRight className="h-4 w-4 shrink-0" aria-hidden="true" />
        )}
        {icon}
        <span>{label}</span>
      </CollapsibleTrigger>
      <CollapsibleContent>{children}</CollapsibleContent>
    </Collapsible>
  )
}

function PlanSteps({ plan }: { plan: string[] }) {
  return (
    <CollapsibleSection
      label={`Execution plan (${plan.length} sub-queries)`}
      icon={<Sparkles className="h-3.5 w-3.5 text-ink" aria-hidden="true" />}
    >
      <div className="mt-2 flex flex-col gap-2 border-l-[1.5px] border-ink/40 pl-4">
        {plan.map((step, i) => (
          <div key={i} className="flex items-start gap-2.5">
            <span className="cg-mono-meta mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center border border-ink/50 text-[10px] text-ink">
              {i + 1}
            </span>
            <span className="text-sm leading-relaxed text-ink-soft">{step}</span>
          </div>
        ))}
      </div>
    </CollapsibleSection>
  )
}

function ReflectionLog({ steps }: { steps: ReflectionStep[] }) {
  return (
    <CollapsibleSection
      label={`Reasoning trace (${steps.length} steps)`}
      icon={<Brain className="h-3.5 w-3.5 text-ink" aria-hidden="true" />}
    >
      <div className="mt-2 flex flex-col gap-3 border-l-[1.5px] border-ink/60 pl-4">
        {steps.map((step, i) => (
          <div key={i} className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="cg-mono-meta flex h-5 w-5 items-center justify-center bg-ink text-[10px] text-paper">
                {step.step}
              </span>
              <span className="cg-overline text-ink-muted">{step.action}</span>
            </div>
            <p className="text-sm leading-relaxed text-ink-soft">{step.observation}</p>
            {step.reasoning && (
              <p className="text-xs italic leading-relaxed text-ink-soft/80">
                {step.reasoning}
              </p>
            )}
          </div>
        ))}
      </div>
    </CollapsibleSection>
  )
}

// ─── Report scaffolding ──────────────────────────────────────────────────────

function SectionShell({
  icon: Icon,
  title,
  count,
  tone = 'solid',
  children,
}: {
  icon: React.ComponentType<{ className?: string }>
  title: string
  count: number
  tone?: 'solid' | 'outline'
  children: React.ReactNode
}) {
  return (
    <section className="border border-ink/25 bg-paper p-5">
      <div className="mb-4 flex items-center gap-2.5 border-b border-ink/20 pb-3">
        <div
          className={cn(
            'flex h-6 w-6 items-center justify-center border',
            tone === 'solid' ? 'border-ink bg-ink text-paper' : 'border-ink/50 text-ink',
          )}
        >
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
        </div>
        <Overline as="h3" className="text-ink">
          {title}
        </Overline>
        {count > 0 && (
          <span className="cg-mono-meta text-xs text-ink-muted">{count}</span>
        )}
      </div>
      {children}
    </section>
  )
}

/** Row marker: filled square (primary assertions) vs outlined square (secondary). */
function RowMarker({ tone }: { tone: 'solid' | 'outline' | 'hatch' }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'mt-1.5 inline-block h-2 w-2 shrink-0',
        tone === 'solid' && 'bg-ink',
        tone === 'outline' && 'border border-ink/70',
        tone === 'hatch' && 'cg-hatch border border-ink/70',
      )}
    />
  )
}

function ConsensusSection({ items }: { items: RawReport['consensus'] }) {
  if (!items || items.length === 0) return null

  return (
    <SectionShell icon={Brain} title="Consensus" count={items.length}>
      <div className="flex flex-col">
        {items.map((item, i) => (
          <div
            key={i}
            className="py-3 [&:not(:first-child)]:border-t [&:not(:first-child)]:border-ink/15"
          >
            <div className="flex gap-3">
              <RowMarker tone="solid" />
              <div className="min-w-0 space-y-2">
                <p className="text-[15px] leading-relaxed text-ink">
                  {item.finding}
                </p>
                {item.citations && item.citations.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {item.citations.map((c, j) => (
                      <CitationChip key={j} id={c} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </SectionShell>
  )
}

function DisputesSection({ items }: { items: RawReport['disputed'] }) {
  if (!items || items.length === 0) return null

  return (
    <SectionShell icon={Swords} title="Disputes" count={items.length} tone="outline">
      <div className="space-y-5">
        {items.map((d, i) => {
          const pa = typeof d.position_a === 'string'
            ? { claim: d.position_a, paper: '?' }
            : d.position_a
          const pb = typeof d.position_b === 'string'
            ? { claim: d.position_b, paper: '?' }
            : d.position_b

          return (
            <div key={i} className="space-y-3">
              <p className="text-[15px] font-medium leading-snug text-ink">{d.topic}</p>
              {/* Two-sided comparison: anchored VS marker centered between panels */}
              <div className="relative grid items-start gap-3 md:grid-cols-[1fr_auto_1fr] md:gap-x-8">
                <div className="min-w-0 border border-ink/25 bg-paper-secondary/60 p-3.5">
                  <div className="mb-2 flex items-center gap-2">
                    <span
                      aria-hidden="true"
                      className="inline-block h-2 w-2 bg-ink"
                    />
                    <Overline className="text-ink-muted">Position A</Overline>
                  </div>
                  <p className="text-sm leading-relaxed text-ink-soft">{pa.claim}</p>
                  {pa.paper && pa.paper !== '?' && (
                    <div className="mt-2">
                      <CitationChip id={pa.paper} />
                    </div>
                  )}
                </div>

                {/* VS medallion — grid-column centered (desktop) */}
                <div className="hidden md:flex md:items-center md:justify-center">
                  <span className="cg-overline border border-ink/40 px-2 py-1 text-ink-muted">
                    VS
                  </span>
                </div>

                <div className="min-w-0 border border-ink/25 bg-paper p-3.5">
                  <div className="mb-2 flex items-center gap-2">
                    <span
                      aria-hidden="true"
                      className="cg-hatch inline-block h-2 w-2 border border-ink"
                    />
                    <Overline className="text-ink-muted">Position B</Overline>
                  </div>
                  <p className="text-sm leading-relaxed text-ink-soft">{pb.claim}</p>
                  {pb.paper && pb.paper !== '?' && (
                    <div className="mt-2">
                      <CitationChip id={pb.paper} />
                    </div>
                  )}
                </div>

                {/* VS for stacked (mobile) layout */}
                <span
                  aria-hidden="true"
                  className="cg-overline w-full text-center text-ink-muted md:hidden"
                >
                  · VS ·
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </SectionShell>
  )
}

function GapsSection({ items }: { items: string[] }) {
  if (!items || items.length === 0) return null

  return (
    <SectionShell icon={HelpCircle} title="Research Gaps" count={items.length} tone="outline">
      <div className="flex flex-col">
        {items.map((gap, i) => (
          <div
            key={i}
            className="flex gap-3 py-2.5 [&:not(:first-child)]:border-t [&:not(:first-child)]:border-ink/15"
          >
            <RowMarker tone="outline" />
            <p className="text-sm leading-relaxed text-ink-soft">{gap}</p>
          </div>
        ))}
      </div>
    </SectionShell>
  )
}

function ExperimentsSection({ items }: { items: string[] }) {
  if (!items || items.length === 0) return null

  return (
    <SectionShell icon={FlaskConical} title="Recommended Experiments" count={items.length}>
      <div className="flex flex-col">
        {items.map((exp, i) => (
          <div
            key={i}
            className="flex gap-3 py-2.5 [&:not(:first-child)]:border-t [&:not(:first-child)]:border-ink/15"
          >
            <RowMarker tone="solid" />
            <p className="text-sm leading-relaxed text-ink-soft">{exp}</p>
          </div>
        ))}
      </div>
    </SectionShell>
  )
}

function SourcesSection({ sources }: { sources: string[] }) {
  if (sources.length === 0) return null

  return (
    <SectionShell icon={BookOpen} title="Sources" count={sources.length} tone="outline">
      <div className="flex flex-wrap gap-2">
        {sources.map((source, i) => {
          const clean = source.replace(/[\[\]]/g, '').trim()
          return (
            <a
              key={i}
              href={arxivUrl(clean)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 border border-ink/35 bg-paper px-3 py-2 text-xs transition-colors duration-150 hover:border-ink hover:bg-ink/5 focus-visible:outline-none"
            >
              <BookOpen className="h-3.5 w-3.5 text-ink" aria-hidden="true" />
              <span className="cg-mono-meta text-ink">{clean}</span>
              <ExternalLink className="h-3 w-3 text-ink-muted" aria-hidden="true" />
            </a>
          )
        })}
      </div>
    </SectionShell>
  )
}

function ReportMarkdown({ report }: { report: string }) {
  return (
    <div className="max-w-[var(--cg-reading-max)] text-[15px] leading-[1.7] text-ink">
      <ReactMarkdown
        components={{
          h1: ({ node: _node, ...props }) => (
            <h1 className="cg-display mt-6 mb-3 text-2xl text-ink" {...props} />
          ),
          h2: ({ node: _node, ...props }) => (
            <h2 className="cg-display mt-5 mb-2.5 text-xl text-ink" {...props} />
          ),
          h3: ({ node: _node, ...props }) => (
            <h3 className="cg-display mt-4 mb-2 text-lg text-ink" {...props} />
          ),
          p: ({ node: _node, ...props }) => <p className="mb-4" {...props} />,
          ul: ({ node: _node, ...props }) => (
            <ul className="mb-4 list-disc space-y-1.5 pl-5" {...props} />
          ),
          ol: ({ node: _node, ...props }) => (
            <ol className="mb-4 list-decimal space-y-1.5 pl-5" {...props} />
          ),
          li: ({ node: _node, ...props }) => (
            <li className="text-[15px] text-ink" {...props} />
          ),
          strong: ({ node: _node, ...props }) => (
            <strong className="font-semibold text-ink" {...props} />
          ),
          blockquote: ({ node: _node, ...props }) => (
            <blockquote
              className="mb-4 border-l-2 border-ink/40 pl-4 italic text-ink-soft"
              {...props}
            />
          ),
          code: ({ node: _node, ...props }) => (
            <code
              className="cg-mono-meta bg-ink/5 px-1.5 py-0.5 text-[13px] text-ink"
              {...props}
            />
          ),
          a: ({ node: _node, ...props }) => {
            const text = props.children?.toString() || ''
            if (
              text.startsWith('arXiv:') ||
              text.match(/^\d{4}\.\d{4,5}$/) ||
              text.startsWith('[arXiv:')
            ) {
              return <CitationChip id={text} />
            }
            return (
              <a
                className="text-ink underline underline-offset-2 hover:bg-ink/5"
                target="_blank"
                rel="noopener noreferrer"
                {...props}
              />
            )
          },
        }}
      >
        {report}
      </ReactMarkdown>
    </div>
  )
}

function SummarySection({ summary }: { summary?: string }) {
  if (!summary?.trim()) return null

  return (
    <section className="border border-ink/25 bg-paper p-5 sm:p-6">
      <div className="mb-3 flex items-center gap-2.5 border-b border-ink/20 pb-3">
        <Overline as="h3" className="text-ink">
          Synthesis summary
        </Overline>
        <QrBlock className="ml-auto" />
      </div>
      <p className="max-w-[var(--cg-reading-max)] whitespace-pre-wrap text-[15px] leading-[1.7] text-ink">
        {summary}
      </p>
    </section>
  )
}

function FullReportSection({ report }: { report?: string }) {
  if (!report?.trim()) return null

  return (
    <details className="group border border-ink/25 bg-paper">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm text-ink-soft transition-colors hover:text-ink focus-visible:outline-none sm:px-5 [&::-webkit-details-marker]:hidden">
        <ChevronRight
          className="h-4 w-4 shrink-0 transition-transform group-open:rotate-90"
          aria-hidden="true"
        />
        <BookOpen className="h-3.5 w-3.5 text-ink" aria-hidden="true" />
        Full generated report
      </summary>
      <div className="border-t border-ink/15 px-4 py-5 sm:px-6">
        <ReportMarkdown report={report} />
      </div>
    </details>
  )
}

// ─── Query history ───────────────────────────────────────────────────────────

interface QueryHistoryItem {
  id: string
  question: string
  timestamp: string
  result: CoordinatorOutput
}

// ─── Main panel ──────────────────────────────────────────────────────────────

interface QueryPanelProps {
  externalQuery?: string | null
  onQueryClear?: () => void
  onLoadingChange?: (loading: boolean) => void
}

export function QueryPanel({ externalQuery, onQueryClear, onLoadingChange }: QueryPanelProps) {
  const [question, setQuestion] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [jobStage, setJobStage] = useState<JobStatus | null>(null)
  const [result, setResult] = useState<CoordinatorOutput | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [history, setHistory] = useState<QueryHistoryItem[]>([])
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null)
  const isClient = useIsClient()
  const lastExternalQuery = useRef<string | null>(null)

  const executeQuery = useCallback(
    async (q: string) => {
      if (!q.trim() || isLoading) return

      setIsLoading(true)
      setError(null)
      setResult(null)
      setJobStage(null)

      try {
        const trimmedQ = q.trim()
        // Submitted as a background job; runQuery polls until the report is ready.
        const output = await runQuery(trimmedQ, { onStatus: setJobStage })
        const normalized = normalizeOutput(output)
        if (!normalized) throw new Error('The query job returned an empty result.')
        setResult(normalized)

        const newItem: QueryHistoryItem = {
          id: makeHistoryId(),
          question: trimmedQ,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          result: normalized,
        }
        setHistory((previous) => [newItem, ...previous].slice(0, MAX_HISTORY))
        setActiveHistoryId(newItem.id)
      } catch (err) {
        setError(
          err instanceof Error ? err.message : 'Failed to get response. Is the API running?'
        )
        setResult(null)
      } finally {
        setIsLoading(false)
        setJobStage(null)
      }
    },
    [isLoading]
  )

  // Load and normalize history after hydration. Older records may not contain
  // sources/plan/reflection fields, so never render raw parsed JSON directly.
  useEffect(() => {
    const saved = safeStorageGet('axion_query_history')
    if (saved) {
      try {
        const parsed = normalizeHistory(JSON.parse(saved))
        if (parsed.length > 0) {
          // One-time hydration from localStorage after mount; a lazy
          // initializer would render different markup on the server.
          // eslint-disable-next-line react-hooks/set-state-in-effect
          setHistory(parsed)
          setActiveHistoryId(parsed[0].id)
          setResult(parsed[0].result)
          setQuestion(parsed[0].question)
        }
      } catch (err) {
        console.warn('Ignoring unreadable query history:', err)
      }
    }
    setHistoryLoaded(true)
  }, [])

  // Persist after the initial read, so an empty first render cannot erase the
  // saved ledger. The command bar listens for the custom event and refreshes.
  useEffect(() => {
    if (!historyLoaded) return
    safeStorageSet('axion_query_history', JSON.stringify(history))
    safeStorageSet(
      'axion-query-history',
      JSON.stringify(history.slice(0, 10).map(({ question, timestamp }) => ({ question, timestamp }))),
    )
    window.dispatchEvent(new Event('axion:query-history'))
  }, [history, historyLoaded])

  // Handle a query handed over from the Command Bar (auto-submit once per query).
  useEffect(() => {
    if (!externalQuery) {
      lastExternalQuery.current = null
      return
    }
    if (!isClient || externalQuery === lastExternalQuery.current) return
    lastExternalQuery.current = externalQuery
    setQuestion(externalQuery)
    onQueryClear?.()
    executeQuery(externalQuery)
  }, [externalQuery, isClient, executeQuery, onQueryClear])

  // Propagate loading state to the parent.
  useEffect(() => {
    onLoadingChange?.(isLoading)
  }, [isLoading, onLoadingChange])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await executeQuery(question)
  }

  const handleSelectHistory = (item: QueryHistoryItem) => {
    setActiveHistoryId(item.id)
    setQuestion(item.question)
    setResult(item.result)
    setError(null)
  }

  const handleDeleteHistory = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    const updated = history.filter((item) => item.id !== id)
    setHistory(updated)
    if (activeHistoryId === id) {
      if (updated.length > 0) {
        setActiveHistoryId(updated[0].id)
        setQuestion(updated[0].question)
        setResult(updated[0].result)
      } else {
        setActiveHistoryId(null)
        setQuestion('')
        setResult(null)
      }
    }
  }

  const handleNewQuery = () => {
    setActiveHistoryId(null)
    setQuestion('')
    setResult(null)
    setError(null)
  }

  const raw: RawReport = result?.raw ? parseRaw(result.raw) : {}
  const confidence = modelConfidence(raw)
  const reportQuestion =
    question || history.find((item) => item.id === activeHistoryId)?.question || ''
  const reportTitle = reportQuestion ? deriveReportTitle(reportQuestion) : 'Research synthesis'
  const sourceCount = result ? (result.source_count ?? result.sources.length) : 0
  const coverageItems = result
    ? [
        {
          label: `iteration${result.iterations !== 1 ? 's' : ''}`,
          value: result.iterations,
        },
        {
          label: `source${sourceCount !== 1 ? 's' : ''} cited`,
          value: sourceCount,
        },
        ...(typeof result.claim_count === 'number'
          ? [
              {
                label: `claim${result.claim_count !== 1 ? 's' : ''} retrieved`,
                value: result.claim_count,
              },
            ]
          : []),
        ...(typeof result.contradiction_count === 'number'
          ? [
              {
                label: `candidate conflict${result.contradiction_count !== 1 ? 's' : ''}`,
                value: result.contradiction_count,
              },
            ]
          : []),
        ...(typeof result.gap_count === 'number'
          ? [
              {
                label: `gap${result.gap_count !== 1 ? 's' : ''} in context`,
                value: result.gap_count,
              },
            ]
          : []),
      ]
    : []

  if (!isClient) {
    return (
      <div className="grid flex-col gap-6 md:grid-cols-12">
        <div className="cg-skeleton h-72 rounded-none md:col-span-4" />
        <div className="md:col-span-8">
          <div className="cg-skeleton mb-4 h-28" />
          <div className="cg-skeleton h-64" />
        </div>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
      {/* ── Sidebar: query history ledger ─────────────────────────────────── */}
      <aside className="order-2 flex max-h-64 flex-col gap-4 border border-ink/30 bg-paper p-4 lg:order-1 lg:col-span-4 lg:max-h-[780px] lg:min-h-[380px]">
        <div className="flex items-center justify-between border-b border-ink/25 pb-3">
          <div className="flex items-center gap-2">
            <History className="h-4 w-4 text-ink" aria-hidden="true" />
            <Overline as="h2" className="text-ink">
              Query History
            </Overline>
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={handleNewQuery}
            className="h-7 gap-1 text-xs"
          >
            <Plus className="h-3 w-3" aria-hidden="true" />
            <span>New</span>
          </Button>
        </div>

        {/* Query ledger list */}
        <div className="flex-1 overflow-y-auto pr-1">
          {history.length === 0 ? (
            <div className="flex flex-col items-start gap-4 py-8 text-left">
              <span className="cg-mono-meta text-xs leading-relaxed text-ink-muted">
                No queries yet. Use the command bar above or the input below.
              </span>
              <PixelGlitch width="w-16" className="opacity-60" />
            </div>
          ) : (
            <ul className="flex flex-col">
              {history.map((item) => {
                const isActive = item.id === activeHistoryId
                return (
                  <li
                    key={item.id}
                    className={cn(
                      'group relative border-b border-ink/10 border-l-2 transition-colors duration-150 last:border-b-0',
                      isActive
                        ? 'border-l-ink bg-ink/5'
                        : 'border-l-transparent hover:bg-ink/[0.03]',
                    )}
                  >
                    <button
                      onClick={() => handleSelectHistory(item)}
                      className="flex w-full items-start gap-3 py-3 pl-3 pr-10 text-left focus-visible:outline-none"
                    >
                      <MessageSquare
                        className={cn(
                          'h-3.5 w-3.5 mt-0.5 flex-shrink-0',
                          isActive ? 'text-ink' : 'text-ink-muted',
                        )}
                        aria-hidden="true"
                      />
                      <span className="min-w-0 flex-1 overflow-hidden">
                        <span
                          className={cn(
                            'block truncate text-[13px] font-medium leading-relaxed',
                            isActive ? 'text-ink' : 'text-ink-soft group-hover:text-ink',
                          )}
                        >
                          {item.question}
                        </span>
                        <span className="cg-mono-meta mt-0.5 block text-[10px] text-ink-muted">
                          {item.timestamp}
                        </span>
                      </span>
                    </button>
                    <button
                      aria-label={`Delete query: ${item.question}`}
                      onClick={(e) => handleDeleteHistory(item.id, e)}
                      className="absolute right-2 top-3 p-1.5 text-ink-muted opacity-100 transition-opacity duration-150 hover:bg-ink/10 hover:text-ink focus-visible:outline-none sm:text-ink-muted sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100"
                    >
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </aside>

      {/* ── Main content: input + report ──────────────────────────────────── */}
      <div className="order-1 min-w-0 space-y-6 lg:order-2 lg:col-span-8">
        {/* Question input */}
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="relative">
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask a research question… e.g., What is the current consensus on transformer scaling laws?"
              aria-label="Research question"
              className="min-h-[110px] w-full resize-none border border-ink/40 bg-paper px-4 py-3.5 text-[15px] leading-relaxed text-ink placeholder:text-ink-muted transition-colors duration-150 hover:border-ink/60 focus:border-ink focus:ring-[3px] focus:ring-ink/15 focus:outline-none disabled:opacity-60"
              disabled={isLoading}
            />
          </div>
          <div className="flex items-center justify-between gap-4">
            <p className="text-xs text-ink-muted">
              Multi-agent synthesis across your knowledge graph
            </p>
            <Button
              type="submit"
              disabled={!question.trim() || isLoading}
              variant="outline"
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  <span>Synthesizing…</span>
                </>
              ) : (
                <>
                  <Search className="h-4 w-4" aria-hidden="true" />
                  <span>Ask</span>
                </>
              )}
            </Button>
          </div>
        </form>

        {/* Loading state */}
        {isLoading && (
          <div
            role="status"
            aria-live="polite"
            className="animate-fade-up border border-ink/40 bg-paper p-6"
          >
            <div className="flex items-start gap-8">
              <div className="min-w-0 flex-1 space-y-3">
                <div className="flex items-center gap-3">
                  <span
                    aria-hidden="true"
                    className="inline-block h-2.5 w-2.5 bg-ink animate-cg-blink"
                  />
                  <span className="text-sm font-medium text-ink">
                    {jobStage === 'queued'
                      ? 'Queued — waiting for a worker…'
                      : 'Synthesizing research intelligence…'}
                  </span>
                </div>
                <div className="ml-[18px] flex flex-col gap-1.5">
                  {[
                    'Plan sub-queries',
                    'Retrieve claims & contradictions',
                    'Reflect on sufficiency',
                    'Synthesize cited report',
                  ].map((step) => (
                    <div key={step} className="flex items-center gap-2.5">
                      <span
                        aria-hidden="true"
                        className="inline-block h-1.5 w-1.5 border border-ink/50"
                      />
                      <span className="cg-mono-meta text-xs text-ink-soft">{step}</span>
                    </div>
                  ))}
                </div>
                <p className="ml-[18px] cg-mono-meta text-[10px] text-ink-muted">
                  This can take up to a minute — the coordinator may iterate a few times.
                </p>
              </div>
              <PixelGlitch width="w-20" className="mt-1 hidden shrink-0 sm:flex" />
            </div>
            <div className="mt-6 flex flex-col gap-3 border-t border-ink/15 pt-5">
              <span className="cg-skeleton h-3 w-full" />
              <span className="cg-skeleton h-3 w-5/6" />
              <span className="cg-skeleton h-3 w-4/5" />
            </div>
          </div>
        )}

        {/* Error state — question is preserved for retry */}
        {error && (
          <ErrorBanner
            title="Request failed"
            message={error}
            className="animate-fade-up"
          />
        )}

        {/* Result */}
        {result && !isLoading && (
          <div className="animate-fade-up space-y-4">
            {/* Report header */}
            <section className="min-w-0 border-[1.5px] border-ink/60 bg-paper p-5 sm:p-6">
              <div className="flex items-start justify-between gap-6">
                <div className="min-w-0 flex-1 space-y-2.5">
                  <Overline>Research Report</Overline>
                  <h2 className="cg-display break-words text-2xl leading-snug text-ink sm:text-3xl">
                    {reportTitle}
                  </h2>
                  {reportQuestion && reportQuestion !== reportTitle && (
                    <p className="max-w-[var(--cg-reading-max)] break-words text-xs leading-relaxed text-ink-soft">
                      <span className="cg-overline mr-2 text-ink-muted">Original question</span>
                      {reportQuestion}
                    </p>
                  )}
                </div>
                <div className="hidden shrink-0 items-start gap-6 sm:flex">
                  <QrBlock />
                  <div className="max-w-[190px] border border-ink/40 px-4 py-3 text-right">
                    <Overline className="text-ink-muted">Model self-assessment</Overline>
                    <p className="cg-mono-meta mt-1 text-xl font-medium text-ink">
                      {confidence.label}
                    </p>
                    <p className="mt-1 text-[10px] leading-snug text-ink-muted">
                      Uncalibrated; not a probability
                    </p>
                  </div>
                </div>
              </div>

              {/* Confidence (mobile, stacked) */}
              <div className="mt-4 flex items-center justify-between gap-3 border border-ink/40 px-4 py-2.5 sm:hidden">
                <div>
                  <Overline className="text-ink-muted">Model self-assessment</Overline>
                  <p className="cg-mono-meta mt-0.5 text-sm text-ink">{confidence.label}</p>
                </div>
                <span className="max-w-[45%] text-right text-[10px] leading-snug text-ink-muted">
                  Uncalibrated; not a probability
                </span>
              </div>

              {raw.confidence_reason && (
                <p className="mt-4 border-t border-ink/20 pt-3 text-xs leading-relaxed text-ink-soft">
                  <span className="cg-overline mr-2 text-ink-muted">
                    {confidence.reported ? 'Model-stated reason' : 'Model note'}
                  </span>
                  {raw.confidence_reason}
                </p>
              )}

              {/* Meta badges */}
              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-ink/20 pt-4">
                {coverageItems.map((item) => (
                  <Badge
                    key={item.label}
                    variant="outline"
                    className="cg-mono-meta text-[11px] font-normal"
                  >
                    <span className="tabular-nums text-ink">{item.value.toLocaleString()}</span>
                    <span className="text-ink-muted">{item.label}</span>
                  </Badge>
                ))}
              </div>

              <div className="mt-4 flex items-start gap-2 border-t border-ink/15 pt-3">
                <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-muted" aria-hidden="true" />
                <p className="text-[11px] leading-relaxed text-ink-soft">
                  <span className="font-medium text-ink">Scope.</span> The synthesizer
                  sees only the retrieved context counted above and may miss relevant
                  work outside this corpus sample. Missing evidence is not evidence of
                  absence, and model labels are not calibrated confidence scores.
                </p>
              </div>
            </section>

            {/* Collapsible reasoning */}
            {(result.plan.length > 0 || result.reflection_log.length > 0) && (
              <div className="border border-ink/25 bg-paper p-4 sm:px-5">
                <div className="divide-y divide-ink/10">
                  {result.plan.length > 0 && (
                    <div>
                      <PlanSteps plan={result.plan} />
                    </div>
                  )}
                  {result.reflection_log.length > 0 && (
                    <div>
                      <ReflectionLog steps={result.reflection_log} />
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Structured report sections */}
            <SummarySection summary={raw.summary} />
            <ConsensusSection items={raw.consensus} />
            <DisputesSection items={raw.disputed} />
            <GapsSection items={raw.missing ?? []} />
            <ExperimentsSection items={raw.recommended_experiments ?? []} />
            <SourcesSection sources={result.sources} />
            <FullReportSection report={result.report} />
          </div>
        )}
      </div>
    </div>
  )
}
