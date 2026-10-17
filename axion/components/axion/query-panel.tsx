'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Search,
  ChevronDown,
  ChevronRight,
  Loader2,
  BookOpen,
  Brain,
  CheckCircle2,
  Swords,
  HelpCircle,
  FlaskConical,
  ExternalLink,
  Sparkles,
  ShieldCheck,
  ShieldAlert,
  ShieldQuestion,
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

function getConfidenceConfig(confidence: number) {
  if (confidence >= 0.8)
    return {
      color: 'text-[#10b981]',
      bg: 'bg-[#10b981]/8',
      border: 'border-[#10b981]/20',
      icon: ShieldCheck,
      label: 'High Confidence',
    }
  if (confidence >= 0.5)
    return {
      color: 'text-[#f59e0b]',
      bg: 'bg-[#f59e0b]/8',
      border: 'border-[#f59e0b]/20',
      icon: ShieldAlert,
      label: 'Medium Confidence',
    }
  return {
    color: 'text-[#f43f5e]',
    bg: 'bg-[#f43f5e]/8',
    border: 'border-[#f43f5e]/20',
    icon: ShieldQuestion,
    label: 'Low Confidence',
  }
}

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

// ─── Sub-components ──────────────────────────────────────────────────────────

function ReflectionLog({ steps }: { steps: ReflectionStep[] }) {
  const [isOpen, setIsOpen] = useState(false)

  if (steps.length === 0) return null

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger className="flex w-full items-center gap-2 py-2 text-sm text-[#94a3b8] hover:text-[#f0f6ff] transition-colors">
        {isOpen ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronRight className="h-4 w-4" />
        )}
        <Brain className="h-4 w-4 text-[#8b5cf6]" />
        <span>Reasoning trace ({steps.length} steps)</span>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-2 space-y-3 border-l-2 border-[#8b5cf6]/30 pl-4">
          {steps.map((step, i) => (
            <div key={i} className="space-y-1 animate-fade-up" style={{ animationDelay: `${i * 50}ms` }}>
              <div className="flex items-center gap-2">
                <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-[#8b5cf6]/15 font-mono text-[10px] text-[#8b5cf6]">
                  {step.step}
                </span>
                <span className="text-xs text-[#475569]">{step.action}</span>
              </div>
              <p className="text-sm text-[#94a3b8] leading-relaxed">{step.observation}</p>
              {step.reasoning && (
                <p className="text-xs text-[#475569] italic">{step.reasoning}</p>
              )}
            </div>
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

function PlanSteps({ plan }: { plan: string[] }) {
  const [isOpen, setIsOpen] = useState(false)

  if (plan.length === 0) return null

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger className="flex w-full items-center gap-2 py-2 text-sm text-[#94a3b8] hover:text-[#f0f6ff] transition-colors">
        {isOpen ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronRight className="h-4 w-4" />
        )}
        <span>Execution plan ({plan.length} sub-queries)</span>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-2 space-y-2 border-l-2 border-[#3b82f6]/30 pl-4">
          {plan.map((step, i) => (
            <div key={i} className="flex items-start gap-2 animate-fade-up" style={{ animationDelay: `${i * 50}ms` }}>
              <span className="mt-0.5 inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-[#3b82f6]/15 font-mono text-[10px] text-[#3b82f6]">
                {i + 1}
              </span>
              <span className="text-sm text-[#94a3b8]">{step}</span>
            </div>
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

function CitationChip({ id }: { id: string }) {
  const clean = id.replace(/[\[\]]/g, '').trim()
  return (
    <a
      href={arxivUrl(clean)}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 rounded-md border border-[#3b82f6]/20 bg-[#3b82f6]/8 px-1.5 py-0.5 font-mono text-[11px] text-[#60a5fa] transition-all duration-150 hover:bg-[#3b82f6]/15 hover:text-[#3b82f6] hover:border-[#3b82f6]/30"
    >
      {clean}
      <ExternalLink className="h-2.5 w-2.5" />
    </a>
  )
}

function SectionHeader({
  icon: Icon,
  title,
  count,
  color,
}: {
  icon: React.ElementType
  title: string
  count?: number
  color: string
}) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <div className={`flex h-7 w-7 items-center justify-center rounded-lg ${color}`}>
        <Icon className="h-3.5 w-3.5" />
      </div>
      <h4 className="font-medium text-[#f0f6ff]">{title}</h4>
      {count !== undefined && count > 0 && (
        <span className="font-mono text-xs text-[#475569]">{count}</span>
      )}
    </div>
  )
}

// ─── Report sections ─────────────────────────────────────────────────────────

function ConsensusSection({ items }: { items: RawReport['consensus'] }) {
  if (!items || items.length === 0) return null

  return (
    <div className="rounded-xl border border-[var(--axion-border-subtle)] axion-surface p-5 axion-card-hover">
      <SectionHeader
        icon={CheckCircle2}
        title="Consensus"
        count={items.length}
        color="bg-[#10b981]/10 text-[#10b981]"
      />
      <div className="space-y-3">
        {items.map((item, i) => (
          <div
            key={i}
            className="flex gap-3 rounded-lg border border-[#10b981]/10 bg-[#10b981]/[0.03] p-3"
          >
            <div className="mt-1 flex-shrink-0">
              <div className="h-1.5 w-1.5 rounded-full bg-[#10b981]" />
            </div>
            <div className="space-y-1.5">
              <p className="text-sm text-[#cbd5e1] leading-relaxed">
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
        ))}
      </div>
    </div>
  )
}

function DisputesSection({ items }: { items: RawReport['disputed'] }) {
  if (!items || items.length === 0) return null

  return (
    <div className="rounded-xl border border-[var(--axion-border-subtle)] axion-surface p-5 axion-card-hover">
      <SectionHeader
        icon={Swords}
        title="Disputes"
        count={items.length}
        color="bg-[#f43f5e]/10 text-[#f43f5e]"
      />
      <div className="space-y-4">
        {items.map((d, i) => {
          const pa = typeof d.position_a === 'string'
            ? { claim: d.position_a, paper: '?' }
            : d.position_a
          const pb = typeof d.position_b === 'string'
            ? { claim: d.position_b, paper: '?' }
            : d.position_b

          return (
            <div
              key={i}
              className="rounded-lg border border-[#f43f5e]/10 bg-[#f43f5e]/[0.03] p-4 space-y-3"
            >
              <p className="text-sm font-medium text-[#f0f6ff]">{d.topic}</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {/* Position A */}
                <div className="rounded-md border border-[var(--axion-border-subtle)] bg-black/40 p-3 space-y-1.5">
                  <div className="flex items-center gap-1.5">
                    <span className="inline-block h-2 w-2 rounded-full bg-[#3b82f6]" />
                    <span className="text-[10px] font-medium uppercase tracking-wider text-[#475569]">
                      Position A
                    </span>
                  </div>
                  <p className="text-xs text-[#94a3b8] leading-relaxed">
                    {pa.claim}
                  </p>
                  {pa.paper && pa.paper !== '?' && (
                    <CitationChip id={pa.paper} />
                  )}
                </div>
                {/* VS Indicator */}
                <div className="hidden sm:flex items-center justify-center absolute left-1/2 -translate-x-1/2 pointer-events-none" />
                {/* Position B */}
                <div className="rounded-md border border-[var(--axion-border-subtle)] bg-black/40 p-3 space-y-1.5">
                  <div className="flex items-center gap-1.5">
                    <span className="inline-block h-2 w-2 rounded-full bg-[#f43f5e]" />
                    <span className="text-[10px] font-medium uppercase tracking-wider text-[#475569]">
                      Position B
                    </span>
                  </div>
                  <p className="text-xs text-[#94a3b8] leading-relaxed">
                    {pb.claim}
                  </p>
                  {pb.paper && pb.paper !== '?' && (
                    <CitationChip id={pb.paper} />
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function GapsSection({ items }: { items: string[] }) {
  if (!items || items.length === 0) return null

  return (
    <div className="rounded-xl border border-[var(--axion-border-subtle)] axion-surface p-5 axion-card-hover">
      <SectionHeader
        icon={HelpCircle}
        title="Research Gaps"
        count={items.length}
        color="bg-[#8b5cf6]/10 text-[#8b5cf6]"
      />
      <div className="space-y-2">
        {items.map((gap, i) => (
          <div
            key={i}
            className="flex gap-3 rounded-lg border border-[#8b5cf6]/10 bg-[#8b5cf6]/[0.03] p-3"
          >
            <HelpCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-[#8b5cf6]/50" />
            <p className="text-sm text-[#94a3b8] leading-relaxed">{gap}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function ExperimentsSection({ items }: { items: string[] }) {
  if (!items || items.length === 0) return null

  return (
    <div className="rounded-xl border border-[var(--axion-border-subtle)] axion-surface p-5 axion-card-hover">
      <SectionHeader
        icon={FlaskConical}
        title="Recommended Experiments"
        count={items.length}
        color="bg-[#3b82f6]/10 text-[#3b82f6]"
      />
      <div className="space-y-2">
        {items.map((exp, i) => (
          <div
            key={i}
            className="flex gap-3 rounded-lg border border-[#3b82f6]/10 bg-[#3b82f6]/[0.03] p-3"
          >
            <FlaskConical className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-[#3b82f6]/50" />
            <p className="text-sm text-[#94a3b8] leading-relaxed">{exp}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function SourcesSection({ sources }: { sources: string[] }) {
  if (sources.length === 0) return null

  return (
    <div className="rounded-xl border border-[var(--axion-border-subtle)] axion-surface p-5 axion-card-hover">
      <SectionHeader
        icon={BookOpen}
        title="Sources"
        count={sources.length}
        color="bg-[#3b82f6]/10 text-[#3b82f6]"
      />
      <div className="flex flex-wrap gap-2">
        {sources.map((source, i) => {
          const clean = source.replace(/[\[\]]/g, '').trim()
          return (
            <a
              key={i}
              href={arxivUrl(clean)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--axion-border-subtle)] bg-[var(--axion-surface-2)] px-3 py-2 text-sm text-[#60a5fa] transition-all duration-150 hover:border-[#3b82f6]/30 hover:bg-[#3b82f6]/10"
            >
              <BookOpen className="h-3.5 w-3.5" />
              <span className="font-mono">{clean}</span>
              <ExternalLink className="h-3 w-3 text-[#475569]" />
            </a>
          )
        })}
      </div>
    </div>
  )
}

function ExecutiveSummarySection({ report }: { report?: string }) {
  if (!report) return null

  return (
    <div className="rounded-xl border border-[var(--axion-border-subtle)] axion-surface p-5 axion-card-hover">
      <SectionHeader
        icon={Sparkles}
        title="Executive Summary"
        color="bg-[#3b82f6]/10 text-[#3b82f6]"
      />
      <div className="text-sm text-[#cbd5e1] leading-relaxed space-y-3">
        <ReactMarkdown
          components={{
            h1: ({ node: _node, ...props}) => <h1 className="text-lg font-bold text-[#f0f6ff] mt-4 mb-2" {...props} />,
            h2: ({ node: _node, ...props}) => <h2 className="text-base font-semibold text-[#f0f6ff] mt-3 mb-2" {...props} />,
            h3: ({ node: _node, ...props}) => <h3 className="text-sm font-semibold text-[#f0f6ff] mt-2 mb-1" {...props} />,
            p: ({ node: _node, ...props}) => <p className="mb-3 last:mb-0" {...props} />,
            ul: ({ node: _node, ...props}) => <ul className="list-disc pl-5 mb-3 space-y-1" {...props} />,
            ol: ({ node: _node, ...props}) => <ol className="list-decimal pl-5 mb-3 space-y-1" {...props} />,
            li: ({ node: _node, ...props}) => <li className="text-sm text-[#94a3b8]" {...props} />,
            strong: ({ node: _node, ...props}) => <strong className="font-semibold text-[#f0f6ff]" {...props} />,
            code: ({ node: _node, ...props}) => <code className="bg-white/5 px-1.5 py-0.5 rounded font-mono text-xs text-[#f0f6ff]" {...props} />,
            a: ({ node: _node, ...props}) => {
              const text = props.children?.toString() || ''
              if (text.startsWith('arXiv:') || text.match(/^\d{4}\.\d{4,5}$/) || text.startsWith('[arXiv:')) {
                return <CitationChip id={text} />
              }
              return <a className="text-[#60a5fa] hover:underline" target="_blank" rel="noopener noreferrer" {...props} />
            }
          }}
        >
          {report}
        </ReactMarkdown>
      </div>
    </div>
  )
}

interface QueryHistoryItem {
  id: string
  question: string
  timestamp: string
  result: CoordinatorOutput
}

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
  const conf = result ? getConfidenceConfig(result.confidence) : null

  if (!isClient) {
    return (
      <div className="rounded-xl border border-[var(--axion-border-subtle)] p-6 space-y-4">
        <div className="animate-shimmer h-24 w-full rounded-lg" />
        <div className="animate-shimmer h-10 w-24 rounded-lg" />
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-12">
      {/* Sidebar - Chat History */}
      <div className="md:col-span-4 border border-[var(--axion-border-subtle)] rounded-xl axion-surface p-4 space-y-4 flex flex-col max-h-[750px] min-h-[400px]">
        <div className="flex items-center justify-between border-b border-[var(--axion-border-subtle)] pb-3">
          <div className="flex items-center gap-2">
            <History className="h-4 w-4 text-[#3b82f6]" />
            <h3 className="font-semibold text-sm text-[#f0f6ff]">History</h3>
          </div>
          <Button
            size="sm"
            onClick={handleNewQuery}
            className="h-7 border border-[#3b82f6]/30 bg-transparent text-[#60a5fa] hover:bg-[#3b82f6]/10 hover:text-white transition-all text-xs flex items-center gap-1"
          >
            <Plus className="h-3 w-3" />
            <span>New</span>
          </Button>
        </div>

        {/* Query List */}
        <div className="flex-1 overflow-y-auto space-y-1.5 pr-1">
          {history.length === 0 ? (
            <div className="text-center py-8 text-[#334155] text-xs">
              No queries yet. Use the command bar or input below.
            </div>
          ) : (
            history.map((item) => {
              const isActive = item.id === activeHistoryId
              return (
                <div
                  key={item.id}
                  onClick={() => handleSelectHistory(item)}
                  className={`group relative flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-all duration-150 ${
                    isActive
                      ? 'border-[#3b82f6]/30 bg-[#3b82f6]/5 text-[#f0f6ff]'
                      : 'border-transparent bg-transparent hover:bg-[rgba(59,130,246,0.04)] text-[#94a3b8]'
                  }`}
                >
                  <MessageSquare className={`h-3.5 w-3.5 mt-0.5 flex-shrink-0 ${isActive ? 'text-[#3b82f6]' : 'text-[#334155]'}`} />
                  <div className="flex-1 pr-6 overflow-hidden">
                    <p className="text-xs font-medium truncate leading-relaxed">{item.question}</p>
                    <span className="text-[10px] text-[#334155] block mt-0.5">{item.timestamp}</span>
                  </div>
                  <button
                    onClick={(e) => handleDeleteHistory(item.id, e)}
                    className="absolute right-2 top-2 p-1 rounded hover:bg-white/5 opacity-0 group-hover:opacity-100 transition-opacity text-[#475569] hover:text-[#f43f5e]"
                    title="Delete query history"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* Main Content Area */}
      <div className="md:col-span-8 space-y-6">
        {/* Question input */}
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="relative">
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask a research question… e.g., What is the current consensus on transformer scaling laws?"
              className="min-h-[100px] w-full resize-none rounded-xl border border-[var(--axion-border-subtle)] bg-[var(--axion-surface-1)] px-4 py-3 text-sm text-[#f0f6ff] placeholder:text-[#334155] focus:border-[#3b82f6]/40 focus:outline-none focus:ring-1 focus:ring-[#3b82f6]/20 focus:shadow-[0_0_20px_rgba(59,130,246,0.08)] transition-all duration-200"
              disabled={isLoading}
            />
          </div>
          <div className="flex items-center justify-between">
            <p className="text-xs text-[#334155]">
              Multi-agent synthesis across your knowledge graph
            </p>
            <Button
              type="submit"
              disabled={!question.trim() || isLoading}
              className="border border-[#3b82f6]/40 bg-[#3b82f6]/5 text-[#60a5fa] hover:bg-[#3b82f6]/10 hover:text-white transition-all duration-150"
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Synthesizing…</span>
                </>
              ) : (
                <>
                  <Search className="h-4 w-4" />
                  <span>Ask</span>
                </>
              )}
            </Button>
          </div>
        </form>

        {/* Loading state */}
        {isLoading && (
          <div className="rounded-xl border border-[#3b82f6]/15 bg-[#3b82f6]/[0.02] p-6 space-y-6 animate-fade-up">
            {/* Indeterminate progress. The query runs as a queued job and
                reports no per-stage progress, so this lists the pipeline
                without pretending stages have completed. */}
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-[#3b82f6]/10">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-[#3b82f6]" />
                </div>
                <span className="text-sm text-[#f0f6ff] font-medium">
                  {jobStage === 'queued'
                    ? 'Queued — waiting for a worker…'
                    : 'Synthesizing research intelligence…'}
                </span>
              </div>
              <div className="ml-9 space-y-2">
                {['Plan sub-queries', 'Retrieve claims & contradictions', 'Reflect on sufficiency', 'Synthesize cited report'].map((step) => (
                  <div key={step} className="flex items-center gap-2 text-xs">
                    <div className="h-1 w-1 rounded-full bg-[#3b82f6]/50" />
                    <span className="text-[#475569]">{step}</span>
                  </div>
                ))}
              </div>
              <p className="ml-9 text-[10px] text-[#334155]">
                This can take up to a minute — the coordinator may iterate a few times.
              </p>
            </div>
            <div className="space-y-3">
              <div className="animate-shimmer h-4 w-full rounded" />
              <div className="animate-shimmer h-4 w-5/6 rounded" style={{ animationDelay: '100ms' }} />
              <div className="animate-shimmer h-4 w-4/5 rounded" style={{ animationDelay: '200ms' }} />
            </div>
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="rounded-xl border border-[#f43f5e]/20 bg-[#f43f5e]/5 p-4 animate-fade-up">
            <p className="text-sm text-[#f43f5e]">{error}</p>
          </div>
        )}

        {/* Result */}
        {result && !isLoading && (
          <div className="space-y-4 animate-fade-up">
            {/* Header card — Question + confidence */}
            <div className="rounded-xl border border-[var(--axion-border-subtle)] axion-surface p-5">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-2 flex-1">
                  <div className="flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-[#3b82f6]" />
                    <span className="text-xs font-medium uppercase tracking-wider text-[#475569]">
                      Research Report
                    </span>
                  </div>
                  <p className="text-[#f0f6ff] font-medium leading-snug">{question}</p>
                </div>
                {conf && (
                  <div
                    className={`flex items-center gap-2 rounded-lg border px-3 py-2 ${conf.bg} ${conf.border}`}
                  >
                    <conf.icon className={`h-4 w-4 ${conf.color}`} />
                    <div className="text-right">
                      <p className={`text-sm font-medium tabular-nums ${conf.color}`}>
                        {Math.round(result.confidence * 100)}%
                      </p>
                      <p className="text-[10px] text-[#475569]">{conf.label}</p>
                    </div>
                  </div>
                )}
              </div>

              {/* Confidence reason */}
              {raw.confidence_reason && (
                <p className="mt-3 text-xs text-[#475569] border-t border-[var(--axion-border-subtle)] pt-3">
                  {raw.confidence_reason}
                </p>
              )}

              {/* Meta badges */}
              <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-[var(--axion-border-subtle)] pt-3">
                <Badge
                  variant="outline"
                  className="border-[var(--axion-border-subtle)] bg-transparent text-[#94a3b8]"
                >
                  {result.iterations} iteration{result.iterations !== 1 ? 's' : ''}
                </Badge>
                {result.sources.length > 0 && (
                  <Badge
                    variant="outline"
                    className="border-[var(--axion-border-subtle)] bg-transparent text-[#60a5fa]"
                  >
                    <BookOpen className="mr-1 h-3 w-3" />
                    {result.sources.length} source{result.sources.length !== 1 ? 's' : ''}
                  </Badge>
                )}
                {raw.consensus && (
                  <Badge
                    variant="outline"
                    className="border-[var(--axion-border-subtle)] bg-transparent text-[#10b981]"
                  >
                    {raw.consensus.length} consensus point{raw.consensus.length !== 1 ? 's' : ''}
                  </Badge>
                )}
                {raw.disputed && raw.disputed.length > 0 && (
                  <Badge
                    variant="outline"
                    className="border-[var(--axion-border-subtle)] bg-transparent text-[#f43f5e]"
                  >
                    {raw.disputed.length} dispute{raw.disputed.length !== 1 ? 's' : ''}
                  </Badge>
                )}
              </div>
            </div>

            {/* Collapsible reasoning */}
            <div className="rounded-xl border border-[var(--axion-border-subtle)] axion-surface p-4">
              <PlanSteps plan={result.plan} />
              <ReflectionLog steps={result.reflection_log} />
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
