'use client'

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import useSWR from 'swr'
import { Loader2, Network, ZoomIn, ZoomOut, Maximize2, ExternalLink, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import { Badge } from '@/components/ui/badge'
import { Overline, ErrorBanner } from '@/components/cg'
import { getGraphData } from '@/lib/api-client'
import { useTheme } from '@/components/theme-provider'
import type { GraphData, GraphNode } from '@/types/axion'

// Dynamic import for react-force-graph-2d (needs window/canvas)
import dynamic from 'next/dynamic'
const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center">
      <Loader2 className="h-6 w-6 animate-spin text-ink" aria-hidden="true" />
    </div>
  ),
})

// ─── Theme-aware palette ─────────────────────────────────────────────────────
// Canvas cannot consume CSS variables directly, so the graph reads the
// theme's RGB triplets after mount/theme changes. The legend uses the same
// variables through CSS, keeping paper light and Cobalt Night in sync.

interface GraphPalette {
  accent: string
  label: string
  halo: string
}

const DEFAULT_PALETTE: GraphPalette = {
  accent: '31, 43, 224',
  label: '31, 43, 224',
  halo: '240, 235, 222',
}

const GAP_SOURCE_LABELS: Record<string, string> = {
  cluster: 'Cluster-derived',
  future_work: 'Future work',
  legacy_import: 'Legacy import',
  sqlite_migration: 'Legacy import',
  unknown: 'Unclassified',
}

function gapSourceLabel(source: string): string {
  const key = source.trim().toLowerCase()
  return GAP_SOURCE_LABELS[key] ?? key.replace(/_/g, ' ')
}

function readGraphPalette(): GraphPalette {
  const styles = getComputedStyle(document.documentElement)
  return {
    accent: styles.getPropertyValue('--cg-graph-accent').trim() || DEFAULT_PALETTE.accent,
    label: styles.getPropertyValue('--cg-graph-label').trim() || DEFAULT_PALETTE.label,
    halo: styles.getPropertyValue('--cg-graph-halo').trim() || DEFAULT_PALETTE.halo,
  }
}

function ink(palette: GraphPalette, alpha: number): string {
  return `rgba(${palette.accent}, ${alpha})`
}

function claimAlpha(node: GraphNode): number {
  const score = node.confidence ?? 0.5
  if (score >= 0.8) return 0.95
  if (score >= 0.5) return 0.55
  return 0.28
}

function getNodeColor(node: GraphNode, palette: GraphPalette): string {
  switch (node.type) {
    case 'paper':
      return ink(palette, 1)
    case 'claim':
      return ink(palette, claimAlpha(node))
    case 'gap':
      return ink(palette, 0.8)
    default:
      return ink(palette, 0.35)
  }
}

function getNodeSize(node: GraphNode): number {
  switch (node.type) {
    case 'paper': return 6
    case 'claim': return 4
    case 'gap': return 5
    default: return 3
  }
}

function getEdgeColor(edge: { type?: string }, palette: GraphPalette): string {
  switch (edge.type) {
    case 'CONTRADICTS': return ink(palette, 0.9)
    case 'SUPPORTS': return ink(palette, 0.5)
    case 'RELATED_TO': return ink(palette, 0.42)
    default: return ink(palette, 0.24)
  }
}

function getEdgeWidth(edge: { type?: string }): number {
  return edge.type === 'CONTRADICTS' ? 1.8 : 0.8
}

function getEdgeDash(edge: { type?: string }): [number, number] | null {
  if (edge.type === 'CONTRADICTS' || edge.type === 'SUPPORTS') return null
  if (edge.type === 'RELATED_TO') return [2, 3]
  return [5, 3]
}

// ─── Legend ──────────────────────────────────────────────────────────────────

function LegendSwatchCircle({ alpha }: { alpha: number }) {
  return (
    <span
      aria-hidden="true"
      style={{ backgroundColor: `rgba(var(--cg-graph-accent), ${alpha})` }}
      className="inline-block h-2.5 w-2.5 rounded-full border border-ink/60"
    />
  )
}

function LegendSwatchDiamond() {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-2 w-2 rotate-45 border-[1.5px]"
      style={{ borderColor: 'rgba(var(--cg-graph-accent), 0.8)' }}
    />
  )
}

function LegendSwatchLine({
  dash,
  width = 1,
}: {
  dash: [number, number] | null
  width?: number
}) {
  return (
    <svg aria-hidden="true" width="16" height="8" className="inline-block shrink-0">
      <line
        x1="0"
        y1="4"
        x2="16"
        y2="4"
        stroke="rgba(var(--cg-graph-accent), 0.72)"
        strokeWidth={width}
        strokeDasharray={dash ? dash.join(' ') : undefined}
      />
    </svg>
  )
}

function Legend() {
  const nodeItems = [
    { label: 'Paper', el: <LegendSwatchCircle alpha={1} /> },
    { label: 'Claim · high score', el: <LegendSwatchCircle alpha={0.95} /> },
    { label: 'Claim · medium', el: <LegendSwatchCircle alpha={0.55} /> },
    { label: 'Claim · low', el: <LegendSwatchCircle alpha={0.28} /> },
    { label: 'Gap', el: <LegendSwatchDiamond /> },
  ]
  const edgeItems = [
    { label: 'Contradicts', dash: null, width: 2 },
    { label: 'Supports', dash: null, width: 1 },
    { label: 'Extracted from', dash: [5, 3] as [number, number], width: 1 },
    { label: 'Gap link', dash: [2, 3] as [number, number], width: 1 },
  ]

  return (
    <details className="absolute bottom-4 left-4 z-10 max-h-[42%] max-w-[min(88vw,290px)] overflow-y-auto border border-ink/40 bg-paper">
      <summary className="cg-overline cursor-pointer list-none px-3 py-2 text-ink-muted focus-visible:bg-ink/5 focus-visible:outline-none [&::-webkit-details-marker]:hidden">
        Legend
      </summary>
      <div className="border-t border-ink/15 px-3 pb-3 pt-2">
        <Overline className="mb-2 text-ink-muted">Nodes</Overline>
        <div className="flex flex-wrap gap-x-3 gap-y-1.5">
          {nodeItems.map((item) => (
            <div key={item.label} className="flex items-center gap-1.5">
              {item.el}
              <span className="text-[11px] text-ink-soft">{item.label}</span>
            </div>
          ))}
        </div>
        <Overline className="mb-1.5 mt-3 text-ink-muted">Edges</Overline>
        <div className="flex flex-col gap-1">
          {edgeItems.map((item) => (
            <div key={item.label} className="flex items-center gap-2">
              <LegendSwatchLine dash={item.dash} width={item.width} />
              <span className="text-[11px] text-ink-soft">{item.label}</span>
            </div>
          ))}
        </div>
      </div>
    </details>
  )
}

// ─── Main component ──────────────────────────────────────────────────────────

export function KnowledgeGraph() {
  // Subscribe to theme changes so canvas colors are re-read on re-render. The
  // pre-paint script has already applied `.dark` before the canvas mounts.
  useTheme()
  const [claimLimit, setClaimLimit] = useState(100)
  const [draftClaimLimit, setDraftClaimLimit] = useState(100)
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const palette =
    typeof document === 'undefined' ? DEFAULT_PALETTE : readGraphPalette()
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const graphRef = useRef<any>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })

  const {
    data: graphData,
    isLoading,
    error,
  } = useSWR<GraphData>(
    `graph-data-${claimLimit}`,
    () => getGraphData(claimLimit),
    { revalidateOnFocus: false }
  )

  // Responsive sizing — fill entire parent and observe layout changes.
  useEffect(() => {
    function updateSize() {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect()
        if (rect.width > 0 && rect.height > 0) {
          setDimensions({ width: rect.width, height: rect.height })
        }
      }
    }
    updateSize()
    const observer = typeof ResizeObserver !== 'undefined'
      ? new ResizeObserver(updateSize)
      : null
    if (containerRef.current) observer?.observe(containerRef.current)
    window.addEventListener('resize', updateSize)
    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', updateSize)
    }
  }, [])

  // Zoom-to-fit after data loads
  useEffect(() => {
    if (graphData && graphRef.current) {
      const timer = setTimeout(() => {
        graphRef.current?.zoomToFit(400, 60)
      }, 800)
      return () => clearTimeout(timer)
    }
  }, [graphData])

  const handleZoomIn = useCallback(() => {
    if (graphRef.current) {
      graphRef.current.zoom(graphRef.current.zoom() * 1.4, 300)
    }
  }, [])

  const handleZoomOut = useCallback(() => {
    if (graphRef.current) {
      graphRef.current.zoom(graphRef.current.zoom() / 1.4, 300)
    }
  }, [])

  const handleZoomToFit = useCallback(() => {
    graphRef.current?.zoomToFit(400, 60)
  }, [])

  // Transform data for react-force-graph. Links with an endpoint outside the
  // claim limit are dropped rather than rendered as disconnected edges, and
  // papers with no claim in the current slice are omitted so they do not form
  // a misleading outer ring.
  const fgData = useMemo(() => {
    if (!graphData) return { nodes: [], links: [] }
    const nodeIds = new Set(graphData.nodes.map((n) => n.id))
    const links = graphData.edges
      .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
      .map((edge) => ({
        source: edge.source,
        target: edge.target,
        type: edge.type,
      }))
    const connectedIds = new Set(
      links.flatMap((edge) => [edge.source, edge.target]),
    )
    return {
      nodes: graphData.nodes.filter(
        (node) => node.type !== 'paper' || connectedIds.has(node.id),
      ),
      links,
    }
  }, [graphData])

  const nodeCounts = useMemo(() => {
    if (!graphData) return null
    const counts = { paper: 0, claim: 0, gap: 0 }
    for (const node of fgData.nodes) {
      if (node.type in counts) counts[node.type as keyof typeof counts]++
    }
    return counts
  }, [graphData, fgData.nodes])

  const edgeCounts = useMemo(() => {
    if (!graphData) return null
    const counts: Record<string, number> = {}
    for (const edge of fgData.links) {
      const type = (edge as { type?: string }).type
      if (type) counts[type] = (counts[type] ?? 0) + 1
    }
    return counts
  }, [graphData, fgData.links])

  const nodeIds = useMemo(
    () => new Set(fgData.nodes.map((node) => node.id)),
    [fgData.nodes],
  )
  const activeSelectedNode =
    selectedNode && nodeIds.has(selectedNode.id) ? selectedNode : null
  const activeHoveredNode =
    hoveredNode && nodeIds.has(hoveredNode.id) ? hoveredNode : null
  const displayedNode = activeSelectedNode ?? activeHoveredNode

  return (
    <div
      ref={containerRef}
      className="relative h-full min-h-[420px] w-full overflow-hidden border border-ink/20"
      role="region"
      aria-label="Knowledge graph: force-directed network of papers, claims, and gaps"
      onMouseLeave={() => setHoveredNode(null)}
    >
      {/* Accessible text alternative for the canvas */}
      {nodeCounts && edgeCounts && (
        <div className="cg-sr-summary">
          Knowledge graph summary: {nodeCounts.paper} papers, {nodeCounts.claim} claims
          (filled by claim score), {nodeCounts.gap} research gaps. Relationship
          counts:{' '}
          {Object.entries(edgeCounts)
            .map(([type, count]) => `${type.toLowerCase().replace(/_/g, ' ')} ${count}`)
            .join(', ')}
          . Select a node on the canvas to inspect it, or use the zoom controls.
        </div>
      )}

      {/* Floating Controls */}
      <div className="absolute right-3 top-3 z-10 flex max-w-[calc(100%-1.5rem)] flex-wrap items-center gap-2 border border-ink/40 bg-paper px-2.5 py-2 sm:right-4 sm:top-4 sm:px-3">
        {graphData && (
          <Badge
            variant="outline"
            className="cg-mono-meta text-[10px] font-normal text-ink-muted"
          >
            {fgData.nodes.length} nodes · {fgData.links.length} edges
          </Badge>
        )}

        <div aria-hidden="true" className="hidden h-4 w-px bg-ink/25 sm:block" />

        <div className="flex items-center gap-2">
          <span className="cg-overline text-ink-muted">Claims</span>
          <div className="w-16 sm:w-20">
            <Slider
              value={[draftClaimLimit]}
              min={25}
              max={200}
              step={25}
              aria-label="Number of claims shown in graph"
              onValueChange={(value: number[]) => setDraftClaimLimit(value[0])}
              onValueCommit={(value: number[]) => setClaimLimit(value[0])}
            />
          </div>
          <span className="cg-mono-meta w-6 text-right text-[10px] text-ink tabular-nums">
            {draftClaimLimit}
          </span>
        </div>

        <div aria-hidden="true" className="hidden h-4 w-px bg-ink/25 sm:block" />

        <div className="flex items-center gap-0.5">
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            aria-label="Zoom in"
            onClick={handleZoomIn}
          >
            <ZoomIn className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            aria-label="Zoom out"
            onClick={handleZoomOut}
          >
            <ZoomOut className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            aria-label="Zoom to fit graph"
            onClick={handleZoomToFit}
          >
            <Maximize2 className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </div>
      </div>

      {error && (
        <div className="absolute inset-x-4 top-24 z-10 mx-auto max-w-xl sm:inset-x-8">
          <ErrorBanner
            title="Graph unavailable"
            message="Failed to load graph data. Is the API running?"
          />
        </div>
      )}

      {isLoading ? (
        <div className="flex h-full min-h-[420px] items-center justify-center">
          <div className="space-y-3 text-center">
            <Loader2 className="mx-auto h-6 w-6 animate-spin text-ink" aria-hidden="true" />
            <p className="cg-mono-meta text-xs text-ink-soft">Loading graph data…</p>
          </div>
        </div>
      ) : graphData && graphData.nodes.length > 0 ? (
        <>
          <ForceGraph2D
            ref={graphRef}
            graphData={fgData}
            width={dimensions.width}
            height={dimensions.height}
            backgroundColor="transparent"
            nodeRelSize={1}
            nodeVal={(node) => getNodeSize(node as GraphNode) ** 2}
            nodeColor={(node) => getNodeColor(node as GraphNode, palette)}
            nodeLabel=""
            nodePointerAreaPaint={(node, color, paintCtx) => {
              const graphNode = node as GraphNode & { x?: number; y?: number }
              paintCtx.beginPath()
              paintCtx.arc(
                graphNode.x ?? 0,
                graphNode.y ?? 0,
                getNodeSize(graphNode) + 4,
                0,
                2 * Math.PI,
              )
              paintCtx.fillStyle = color
              paintCtx.fill()
            }}
            linkColor={(link) => getEdgeColor(link as { type?: string }, palette)}
            linkWidth={(link) => getEdgeWidth(link as { type?: string })}
            linkLineDash={(link) => getEdgeDash(link as { type?: string })}
            linkDirectionalArrowLength={3}
            linkDirectionalArrowRelPos={1}
            linkDirectionalArrowColor={(link) =>
              getEdgeColor(link as { type?: string }, palette)
            }
            cooldownTicks={120}
            onNodeHover={(node) => setHoveredNode((node as GraphNode | null) ?? null)}
            onNodeClick={(node) => {
              const graphNode = node as GraphNode
              setSelectedNode((previous) =>
                previous?.id === graphNode.id ? null : graphNode,
              )
            }}
            onBackgroundClick={() => {
              setSelectedNode(null)
              setHoveredNode(null)
            }}
            enableNodeDrag={true}
            enableZoomInteraction={true}
            nodeCanvasObject={(node, ctx: CanvasRenderingContext2D, globalScale: number) => {
              const graphNode = node as GraphNode & { x?: number; y?: number }
              const size = (getNodeSize(graphNode) / globalScale) * 2
              const x = graphNode.x ?? 0
              const y = graphNode.y ?? 0

              if (graphNode.type === 'paper') {
                ctx.beginPath()
                ctx.arc(x, y, size + 2 / globalScale, 0, 2 * Math.PI)
                ctx.fillStyle = ink(palette, 0.1)
                ctx.fill()
                ctx.beginPath()
                ctx.arc(x, y, size, 0, 2 * Math.PI)
                ctx.fillStyle = getNodeColor(graphNode, palette)
                ctx.fill()
                ctx.lineWidth = 0.5 / globalScale
                ctx.strokeStyle = ink(palette, 0.55)
                ctx.stroke()
              } else if (graphNode.type === 'claim') {
                ctx.beginPath()
                ctx.arc(x, y, size, 0, 2 * Math.PI)
                ctx.fillStyle = ink(palette, claimAlpha(graphNode))
                ctx.fill()
                ctx.beginPath()
                ctx.arc(x, y, size, 0, 2 * Math.PI)
                ctx.lineWidth = 0.7 / globalScale
                ctx.strokeStyle = ink(palette, 0.8)
                ctx.stroke()
              } else if (graphNode.type === 'gap') {
                const radius = size * 1.35
                ctx.beginPath()
                ctx.moveTo(x, y - radius)
                ctx.lineTo(x + radius, y)
                ctx.lineTo(x, y + radius)
                ctx.lineTo(x - radius, y)
                ctx.closePath()
                ctx.lineWidth = 1.5 / globalScale
                ctx.strokeStyle = ink(palette, 0.85)
                ctx.stroke()
                ctx.fillStyle = ink(palette, 0.12)
                ctx.fill()
              } else {
                ctx.beginPath()
                ctx.arc(x, y, size, 0, 2 * Math.PI)
                ctx.fillStyle = ink(palette, 0.35)
                ctx.fill()
              }

              // Labels at deep zoom, plus the hovered/selected node at any zoom.
              const showLabel =
                globalScale > 2.5 ||
                displayedNode?.id === graphNode.id
              if (showLabel && graphNode.label) {
                const fontSize = Math.max(2, 10 / globalScale)
                const label =
                  graphNode.label.length > 42
                    ? `${graphNode.label.slice(0, 42)}…`
                    : graphNode.label
                ctx.font = `${fontSize}px 'Hanken Grotesk', sans-serif`
                ctx.textAlign = 'center'
                ctx.textBaseline = 'top'
                ctx.lineWidth = 3 / globalScale
                ctx.strokeStyle = `rgba(${palette.halo}, 0.9)`
                ctx.strokeText(label, x, y + size + 3 / globalScale)
                ctx.fillStyle = `rgba(${palette.label}, 0.95)`
                ctx.fillText(label, x, y + size + 3 / globalScale)
              }
            }}
          />
          <Legend />
        </>
      ) : (
        <div className="flex h-full min-h-[420px] items-center justify-center p-4">
          <div className="border border-ink/25 bg-paper px-6 py-8 text-center sm:px-10">
            <Network className="mx-auto h-8 w-8 text-ink-muted" aria-hidden="true" />
            <p className="cg-display mt-3 text-xl text-ink">No graph data available</p>
            <p className="mt-1.5 text-sm text-ink-soft">
              Ingest papers first to populate the knowledge graph.
            </p>
          </div>
        </div>
      )}

      {displayedNode && (
        <div className="animate-fade-up absolute inset-x-3 bottom-3 z-20 max-h-[45%] overflow-y-auto border-[1.5px] border-ink/60 bg-paper p-3.5 sm:inset-x-auto sm:bottom-4 sm:right-4 sm:w-80">
          <div className="flex items-start justify-between gap-3">
            <Badge
              variant="outline"
              className="cg-overline border-ink/50 bg-transparent font-semibold text-ink"
            >
              {displayedNode.type}
            </Badge>
            {activeSelectedNode && (
              <button
                type="button"
                onClick={() => {
                  setSelectedNode(null)
                  setHoveredNode(null)
                }}
                aria-label="Close node details"
                className="p-1 text-ink-muted transition-colors hover:bg-ink/10 hover:text-ink focus-visible:outline-none"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            )}
          </div>

          <p className="mt-2 break-words text-sm leading-snug text-ink">
            {displayedNode.text || displayedNode.label}
          </p>

          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-ink/15 pt-1.5 text-[11px] text-ink-soft">
            {displayedNode.year && <span>{displayedNode.year}</span>}
            {displayedNode.section && <span>{displayedNode.section}</span>}
            {displayedNode.source && (
              <span>source: {gapSourceLabel(displayedNode.source)}</span>
            )}
            {displayedNode.confidence !== undefined &&
              displayedNode.confidence !== null && (
                <span
                  className="cg-mono-meta text-ink tabular-nums"
                  title="Model-reported score; not calibrated."
                >
                  {Math.round(displayedNode.confidence * 100)}%{' '}
                  {displayedNode.type === 'gap' ? 'model score' : 'claim score'}
                </span>
              )}
          </div>

          {displayedNode.paper_title && displayedNode.type !== 'paper' && (
            <p className="mt-2 line-clamp-2 break-words text-[11px] leading-relaxed text-ink-soft">
              {displayedNode.paper_title}
            </p>
          )}

          {displayedNode.arxiv_id && (
            <a
              href={`https://arxiv.org/abs/${displayedNode.arxiv_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 inline-flex items-center gap-1.5 text-[11px] text-ink underline decoration-ink/30 underline-offset-2 hover:bg-ink/5 focus-visible:outline-none"
            >
              <span className="cg-mono-meta">{displayedNode.arxiv_id}</span>
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
              <span className="sr-only">opens on arXiv in a new tab</span>
            </a>
          )}
        </div>
      )}
    </div>
  )
}
