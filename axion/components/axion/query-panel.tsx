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
  confidenceLevel,
} from '@/components/cg'

// ─── Raw report JSON type from the coordinator ──────────────────────────────

interface RawReport {
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

function parseRaw(rawStr: string): RawReport {
  try {
    return JSON.parse(rawStr)
  } catch {
    return {}
  }
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
              <span className="cg-overline text-ink/50">{step.action}</span>
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
          <span className="cg-mono-meta text-xs text-ink/50">{count}</span>
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
                    <Overline className="text-ink/60">Position A</Overline>
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
                  <span className="cg-overline border border-ink/40 px-2 py-1 text-ink/70">
                    VS
                  </span>
                </div>

                <div className="min-w-0 border border-ink/25 bg-paper p-3.5">
                  <div className="mb-2 flex items-center gap-2">
                    <span
                      aria-hidden="true"
                      className="cg-hatch inline-block h-2 w-2 border border-ink"
                    />
                    <Overline className="text-ink/60">Position B</Overline>
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
                  className="cg-overline w-full text-center text-ink/40 md:hidden"
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
              <ExternalLink className="h-3 w-3 text-ink/50" aria-hidden="true" />
            </a>
          )
        })}
      </div>
    </SectionShell>
  )
}

function ExecutiveSummarySection({ report }: { report?: string }) {
  if (!report) return null

  return (
    <section className="border border-ink/25 bg-paper p-6">
      <div className="mb-4 flex items-center gap-2.5 border-b border-ink/20 pb-3">
        <Overline as="h3" className="text-ink">
          Executive Summary
        </Overline>
        <QrBlock className="ml-auto" />
      </div>
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
    </section>
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
        setResult(output)

        // Add to history
        const newItem: QueryHistoryItem = {
          id: Math.random().toString(36).substring(7),
          question: trimmedQ,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          result: output,
        }
        const updated = [newItem, ...history]
        setHistory(updated)
        localStorage.setItem('axion_query_history', JSON.stringify(updated))
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
    [history, isLoading]
  )

  // Load history from localStorage after hydration.
  useEffect(() => {
    const saved = localStorage.getItem('axion_query_history')
    if (saved) {
      try {
        const parsed = JSON.parse(saved)
        if (Array.isArray(parsed)) {
          setHistory(parsed)
          if (parsed.length > 0) {
            setActiveHistoryId(parsed[0].id)
            setResult(parsed[0].result)
            setQuestion(parsed[0].question)
          }
        }
      } catch (e) {
        console.error('Failed to parse query history:', e)
      }
    }
  }, [])

  // Persist history to localStorage for the command bar's recent-query list.
  useEffect(() => {
    if (isClient && history.length > 0) {
      localStorage.setItem('axion-query-history', JSON.stringify(history))
    }
  }, [history, isClient])

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
    localStorage.setItem('axion_query_history', JSON.stringify(updated))
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
  const confidenceLevelValue = result ? confidenceLevel(result.confidence) : null

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
      <aside className="flex max-h-[780px] min-h-[380px] flex-col gap-4 border border-ink/30 bg-paper p-4 lg:col-span-4">
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
              <span className="cg-mono-meta text-xs leading-relaxed text-ink/50">
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
                          isActive ? 'text-ink' : 'text-ink/40',
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
                        <span className="cg-mono-meta mt-0.5 block text-[10px] text-ink/40">
                          {item.timestamp}
                        </span>
                      </span>
                    </button>
                    <button
                      aria-label={`Delete query: ${item.question}`}
                      onClick={(e) => handleDeleteHistory(item.id, e)}
                      className="absolute right-2 top-3 p-1.5 text-ink/40 opacity-0 transition-opacity duration-150 hover:bg-ink/10 hover:text-ink focus-visible:opacity-100 focus-visible:outline-none group-hover:opacity-100"
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
      <div className="min-w-0 space-y-6 lg:col-span-8">
        {/* Question input */}
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="relative">
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask a research question… e.g., What is the current consensus on transformer scaling laws?"
              aria-label="Research question"
              className="min-h-[110px] w-full resize-none border border-ink/40 bg-paper px-4 py-3.5 text-[15px] leading-relaxed text-ink placeholder:text-ink/35 transition-colors duration-150 hover:border-ink/60 focus:border-ink focus:ring-[3px] focus:ring-ink/15 focus:outline-none disabled:opacity-60"
              disabled={isLoading}
            />
          </div>
          <div className="flex items-center justify-between gap-4">
            <p className="text-xs text-ink/50">
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
          <div className="animate-fade-up border border-ink/40 bg-paper p-6">
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
                <p className="ml-[18px] cg-mono-meta text-[10px] text-ink/40">
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
            <section className="border-[1.5px] border-ink/60 bg-paper p-6">
              <div className="flex items-start justify-between gap-6">
                <div className="min-w-0 flex-1 space-y-2.5">
                  <Overline>Research Report</Overline>
                  <p className="cg-display text-2xl leading-snug text-ink sm:text-3xl">
                    {question}
                  </p>
                </div>
                <div className="hidden shrink-0 items-start gap-6 sm:flex">
                  <QrBlock />
                  <div className="border border-ink/40 px-4 py-3 text-right">
                    <Overline className="text-ink/60">
                      {confidenceLevelValue?.toUpperCase()}
                    </Overline>
                    <p className="cg-mono-meta mt-1 text-2xl font-medium text-ink tabular-nums">
                      {Math.round(result.confidence * 100)}%
                    </p>
                    <Overline className="mt-1 text-ink/50">
                      Confidence
                    </Overline>
                  </div>
                </div>
              </div>

              {/* Confidence (mobile, stacked) */}
              {confidenceLevelValue !== null && (
                <div className="mt-4 flex items-center justify-between border border-ink/40 px-4 py-2.5 sm:hidden">
                  <span className="cg-mono-meta text-lg text-ink tabular-nums">
                    {Math.round(result.confidence * 100)}%
                  </span>
                  <Overline className="text-ink/60">
                    {confidenceLevelValue} confidence
                  </Overline>
                </div>
              )}

              {raw.confidence_reason && (
                <p className="mt-4 border-t border-ink/20 pt-3 text-xs leading-relaxed text-ink-soft">
                  {raw.confidence_reason}
                </p>
              )}

              {/* Meta badges */}
              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-ink/20 pt-4">
                <Badge
                  variant="outline"
                  className="cg-mono-meta text-[11px] font-normal"
                >
                  {result.iterations} iteration{result.iterations !== 1 ? 's' : ''}
                </Badge>
                {result.sources.length > 0 && (
                  <Badge
                    variant="outline"
                    className="cg-mono-meta text-[11px] font-normal"
                  >
                    <BookOpen className="h-3 w-3" aria-hidden="true" />
                    {result.sources.length} source{result.sources.length !== 1 ? 's' : ''}
                  </Badge>
                )}
                {raw.consensus && (
                  <Badge
                    variant="outline"
                    className="cg-mono-meta text-[11px] font-normal"
                  >
                    {raw.consensus.length} consensus point{raw.consensus.length !== 1 ? 's' : ''}
                  </Badge>
                )}
                {raw.disputed && raw.disputed.length > 0 && (
                  <Badge
                    variant="outline"
                    className="cg-mono-meta text-[11px] font-normal"
                  >
                    {raw.disputed.length} dispute{raw.disputed.length !== 1 ? 's' : ''}
                  </Badge>
                )}
              </div>
            </section>

            {/* Collapsible reasoning */}
            <div className="border border-ink/25 bg-paper p-4 sm:px-5">
              <div className="divide-y divide-ink/10">
                <div>
                  <PlanSteps plan={result.plan} />
                </div>
                <div>
                  <ReflectionLog steps={result.reflection_log} />
                </div>
              </div>
            </div>

            {/* Structured report sections */}
            <ExecutiveSummarySection report={result.report} />
            <ConsensusSection items={raw.consensus} />
            <DisputesSection items={raw.disputed} />
            <GapsSection items={raw.missing ?? []} />
            <ExperimentsSection items={raw.recommended_experiments ?? []} />
            <SourcesSection sources={result.sources} />
          </div>
        )}
      </div>
    </div>
  )
}
