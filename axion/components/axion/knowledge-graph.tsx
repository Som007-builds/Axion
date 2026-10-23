'use client'

import { useState, useCallback, useRef, useEffect } from 'react'
import useSWR from 'swr'
import { Loader2, Network, ZoomIn, ZoomOut, Maximize2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import { Badge } from '@/components/ui/badge'
import { Overline, ErrorBanner } from '@/components/cg'
import { getGraphData } from '@/lib/api-client'
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

// ─── Monochrome encoding ─────────────────────────────────────────────────────
// One ink. Entity types are distinguished by shape and fill, edges by line
// weight and dash pattern. Confidence is encoded by fill opacity and always
// available numerically in the hover card.

const INK_RGB = '31, 43, 224'

function ink(a: number): string {
  return `rgba(${INK_RGB}, ${a})`
}

function claimAlpha(node: GraphNode): number {
  const c = node.confidence ?? 0.5
  if (c >= 0.8) return 0.95
  if (c >= 0.5) return 0.5
  return 0.16
}

function getNodeColor(node: GraphNode): string {
  switch (node.type) {
    case 'paper':
      return ink(1)
    case 'claim':
      return ink(claimAlpha(node))
    case 'gap':
      return ink(0.75)
    default:
      return ink(0.35)
  }
}

function getNodeSize(node: GraphNode): number {
  switch (node.type) {
    case 'paper': return 6
    case 'claim': return 4
    case 'gap':   return 5
    default:      return 3
  }
}

function getEdgeColor(edge: { type?: string }): string {
  switch (edge.type) {
    case 'CONTRADICTS':    return ink(0.85)
    case 'SUPPORTS':       return ink(0.45)
    case 'RELATES_TO':     return ink(0.35)
    default:               return ink(0.2)
  }
}

function getEdgeWidth(edge: { type?: string }): number {
  return edge.type === 'CONTRADICTS' ? 1.8 : 0.8
}

// ─── Legend ──────────────────────────────────────────────────────────────────

function LegendSwatchCircle({ alpha }: { alpha: number }) {
  return (
    <span
      aria-hidden="true"
      style={{ backgroundColor: `rgba(${INK_RGB}, ${alpha})` }}
      className="inline-block h-2.5 w-2.5 rounded-full"
    />
  )
}

function LegendSwatchDiamond() {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-2 w-2 rotate-45 border-[1.5px]"
      style={{ borderColor: `rgba(${INK_RGB}, 0.75)` }}
    />
  )
}

function LegendSwatchLine({ dashed, width = 1 }: { dashed: boolean; width?: number }) {
  return (
    <svg aria-hidden="true" width="16" height="8" className="inline-block shrink-0">
      <line
        x1="0"
        y1="4"
        x2="16"
        y2="4"
        stroke={`rgba(${INK_RGB}, 0.7)`}
        strokeWidth={width}
        strokeDasharray={dashed ? '4 3' : undefined}
      />
    </svg>
  )
}

function Legend() {
  const nodeItems = [
    { label: 'Paper', el: <LegendSwatchCircle alpha={1} /> },
    { label: 'Claim · High', el: <LegendSwatchCircle alpha={0.95} /> },
    { label: 'Claim · Medium', el: <LegendSwatchCircle alpha={0.5} /> },
    { label: 'Claim · Low', el: <LegendSwatchCircle alpha={0.16} /> },
    { label: 'Gap', el: <LegendSwatchDiamond /> },
  ]
  const edgeItems = [
    { label: 'Contradicts', dashed: false, width: 2 },
    { label: 'Supports', dashed: false, width: 1 },
    { label: 'Relates / Extracted From', dashed: true, width: 1 },
  ]

  return (
    <div className="absolute bottom-4 left-4 z-10 max-w-[min(92vw,280px)] border border-ink/40 bg-paper p-3">
      <Overline className="mb-2 text-ink/60">Nodes</Overline>
      <div className="flex flex-wrap gap-x-3 gap-y-1.5">
        {nodeItems.map((item) => (
          <div key={item.label} className="flex items-center gap-1.5">
            {item.el}
            <span className="text-[11px] text-ink-soft">{item.label}</span>
          </div>
        ))}
      </div>
      <Overline className="mb-1.5 mt-3 text-ink/60">Edges</Overline>
      <div className="flex flex-col gap-1">
        {edgeItems.map((item) => (
          <div key={item.label} className="flex items-center gap-2">
            <LegendSwatchLine dashed={item.dashed} width={item.width} />
            <span className="text-[11px] text-ink-soft">{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Main component ──────────────────────────────────────────────────────────

export function KnowledgeGraph() {
  const [claimLimit, setClaimLimit] = useState(100)
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null)
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

  // Responsive sizing — fill entire parent
  useEffect(() => {
    function updateSize() {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect()
        setDimensions({ width: rect.width, height: rect.height })
      }
    }
    updateSize()
    window.addEventListener('resize', updateSize)
    return () => window.removeEventListener('resize', updateSize)
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
      const currentZoom = graphRef.current.zoom()
      graphRef.current.zoom(currentZoom * 1.4, 300)
    }
  }, [])

  const handleZoomOut = useCallback(() => {
    if (graphRef.current) {
      const currentZoom = graphRef.current.zoom()
      graphRef.current.zoom(currentZoom / 1.4, 300)
    }
  }, [])

  const handleZoomToFit = useCallback(() => {
    graphRef.current?.zoomToFit(400, 60)
  }, [])

  // Transform data for react-force-graph
  const fgData = (() => {
    if (!graphData) return { nodes: [], links: [] }
    const nodeIds = new Set(graphData.nodes.map((n) => n.id))
    return {
      nodes: graphData.nodes.map((n) => ({ ...n })),
      links: graphData.edges
        .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
        .map((e) => ({
          source: e.source,
          target: e.target,
          type: e.type,
        })),
    }
  })()

  const nodeCounts = (() => {
    if (!graphData) return null
    const counts = { paper: 0, claim: 0, gap: 0 }
    for (const n of graphData.nodes) {
      if (n.type in counts) counts[n.type as keyof typeof counts]++
    }
    return counts
  })()

  const edgeCounts = (() => {
    if (!graphData) return null
    const counts: Record<string, number> = {}
    for (const e of graphData.edges) {
      counts[e.type] = (counts[e.type] ?? 0) + 1
    }
    return counts
  })()

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full overflow-hidden"
      role="application"
      aria-label="Knowledge graph: force-directed network of papers, claims, and gaps"
    >
      {/* Accessible text alternative for the canvas */}
      {nodeCounts && edgeCounts && (
        <div className="cg-sr-summary">
          Knowledge graph summary: {nodeCounts.paper} papers,{' '}
          {nodeCounts.claim} claims (colored by confidence via fill density),{' '}
          {nodeCounts.gap} research gaps. Relationship counts:{' '}
          {Object.entries(edgeCounts)
            .map(([type, n]) => `${type.toLowerCase().replace(/_/g, ' ')} ${n}`)
            .join(', ')}
          . Interact with the zoom controls or drag nodes to explore the graph.
        </div>
      )}

      {/* Floating Controls */}
      <div className="absolute right-4 top-4 z-10 flex max-w-[calc(100%-2rem)] flex-wrap items-center gap-2 border border-ink/40 bg-paper px-3 py-2">
        {/* Node count */}
        {graphData && (
          <Badge
            variant="outline"
            className="cg-mono-meta text-[10px] font-normal text-ink/60"
          >
            {graphData.nodes.length} nodes · {graphData.edges.length} edges
          </Badge>
        )}

        <div aria-hidden="true" className="h-4 w-px bg-ink/25" />

        {/* Claim limit slider */}
        <div className="flex items-center gap-2">
          <span className="cg-overline text-ink/50">Claims</span>
          <div className="w-20">
            <Slider
              defaultValue={[claimLimit]}
              min={25}
              max={200}
              step={25}
              aria-label="Number of claims shown in graph"
              onValueCommit={(val: number[]) => setClaimLimit(val[0])}
            />
          </div>
          <span className="cg-mono-meta w-6 text-right text-[10px] text-ink tabular-nums">
            {claimLimit}
          </span>
        </div>

        <div aria-hidden="true" className="h-4 w-px bg-ink/25" />

        {/* Zoom controls */}
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
            aria-label="Zoom to fit"
            onClick={handleZoomToFit}
          >
            <Maximize2 className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="absolute inset-x-8 top-20 z-10 mx-auto max-w-xl">
          <ErrorBanner
            title="Graph unavailable"
            message="Failed to load graph data. Is the API running?"
          />
        </div>
      )}

      {/* Graph canvas */}
      {isLoading ? (
        <div className="flex h-full items-center justify-center">
          <div className="space-y-3 text-center">
            <Loader2
              className="mx-auto h-6 w-6 animate-spin text-ink"
              aria-hidden="true"
            />
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
            nodeColor={(node) => getNodeColor(node as GraphNode)}
            nodeLabel=""
            linkColor={(link) => getEdgeColor(link as { type?: string })}
            linkWidth={(link) => getEdgeWidth(link as { type?: string })}
            linkLineDash={(link) => {
              const t = (link as { type?: string }).type
              if (t === 'CONTRADICTS' || t === 'SUPPORTS') return null
              return [4, 4]
            }}
            linkDirectionalArrowLength={3}
            linkDirectionalArrowRelPos={1}
            linkDirectionalArrowColor={(link) => getEdgeColor(link as { type?: string })}
            cooldownTicks={120}
            onNodeHover={(node) => setHoveredNode((node as GraphNode | null) ?? null)}
            enableNodeDrag={true}
            enableZoomInteraction={true}
            nodeCanvasObject={(node, ctx: CanvasRenderingContext2D, globalScale: number) => {
              const gn = node as GraphNode & { x?: number; y?: number }
              const size = getNodeSize(gn) / globalScale * 2
              const x = gn.x ?? 0
              const y = gn.y ?? 0

              if (gn.type === 'paper') {
                // Paper: solid cobalt dot with a light structural halo
                ctx.beginPath()
                ctx.arc(x, y, size + 2, 0, 2 * Math.PI)
                ctx.fillStyle = ink(0.1)
                ctx.fill()
                ctx.beginPath()
                ctx.arc(x, y, size, 0, 2 * Math.PI)
                ctx.fillStyle = ink(1)
                ctx.fill()
                ctx.lineWidth = 0.3
                ctx.strokeStyle = ink(0.5)
                ctx.stroke()
              } else if (gn.type === 'claim') {
                // Claim: dot filled by confidence density
                ctx.beginPath()
                ctx.arc(x, y, size, 0, 2 * Math.PI)
                ctx.fillStyle = ink(claimAlpha(gn))
                ctx.fill()
                ctx.beginPath()
                ctx.arc(x, y, size, 0, 2 * Math.PI)
                ctx.lineWidth = 0.4
                ctx.strokeStyle = ink(0.75)
                ctx.stroke()
              } else if (gn.type === 'gap') {
                // Gap: hollow diamond
                const r = size * 1.35
                ctx.beginPath()
                ctx.moveTo(x, y - r)
                ctx.lineTo(x + r, y)
                ctx.lineTo(x, y + r)
                ctx.lineTo(x - r, y)
                ctx.closePath()
                ctx.lineWidth = 1.1 / Math.max(globalScale, 1) * 2
                ctx.strokeStyle = ink(0.8)
                ctx.stroke()
                ctx.fillStyle = ink(0.1)
                ctx.fill()
              } else {
                ctx.beginPath()
                ctx.arc(x, y, size, 0, 2 * Math.PI)
                ctx.fillStyle = ink(0.35)
                ctx.fill()
              }

              // Label at high zoom
              if (globalScale > 2.5 && gn.label) {
                ctx.font = `${Math.max(2, 10 / globalScale)}px 'Hanken Grotesk', sans-serif`
                ctx.textAlign = 'center'
                ctx.textBaseline = 'top'
                ctx.fillStyle = ink(0.75)
                ctx.fillText(
                  gn.label.length > 25 ? gn.label.slice(0, 25) + '…' : gn.label,
                  x,
                  y + size + 2
                )
              }
            }}
          />
          <Legend />
        </>
      ) : (
        <div className="flex h-full items-center justify-center">
          <div className="border border-ink/25 bg-paper px-10 py-8 text-center">
            <Network className="mx-auto h-8 w-8 text-ink/40" aria-hidden="true" />
            <p className="cg-display mt-3 text-xl text-ink">No graph data available</p>
            <p className="mt-1.5 text-sm text-ink-soft">
              Ingest some papers first to populate the knowledge graph
            </p>
          </div>
        </div>
      )}

      {/* Hover details */}
      {hoveredNode && (
        <div className="animate-fade-up absolute right-4 top-20 z-20 max-w-xs min-w-[220px] border-[1.5px] border-ink/60 bg-paper p-3.5">
          <div className="flex items-center gap-2">
            <Badge
              variant="outline"
              className="cg-overline border-ink/50 bg-transparent font-semibold text-ink"
            >
              {hoveredNode.type}
            </Badge>
          </div>
          <p className="mt-2 text-sm leading-snug text-ink">{hoveredNode.label}</p>
          {hoveredNode.confidence !== undefined && (
            <p className="mt-1.5 border-t border-ink/15 pt-1.5 text-xs text-ink-soft">
              Confidence:{' '}
              <span className="cg-mono-meta font-medium text-ink tabular-nums">
                {Math.round(hoveredNode.confidence * 100)}%
              </span>
            </p>
          )}
        </div>
      )}
    </div>
  )
}
