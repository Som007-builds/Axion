'use client'

import { useState, useCallback, useRef, useEffect } from 'react'
import useSWR from 'swr'
import { Loader2, Network, ZoomIn, ZoomOut, Maximize2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import { Badge } from '@/components/ui/badge'
import { getGraphData } from '@/lib/api-client'
import type { GraphData, GraphNode, GraphEdge } from '@/types/axion'

// Dynamic import for react-force-graph-2d (needs window/canvas)
import dynamic from 'next/dynamic'
const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center">
      <Loader2 className="h-8 w-8 animate-spin text-[#3b82f6]" />
    </div>
  ),
})

// ─── Color helpers ───────────────────────────────────────────────────────────

function getNodeColor(node: GraphNode): string {
  switch (node.type) {
    case 'paper':
      return '#3b82f6' // sapphire blue
    case 'claim': {
      const c = node.confidence ?? 0.5
      if (c >= 0.8) return '#10b981'   // green — high
      if (c >= 0.5) return '#f59e0b'   // amber — medium
      return '#f43f5e'                  // rose — low
    }
    case 'gap':
      return '#8b5cf6' // violet
    default:
      return '#475569'
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
    case 'CONTRADICTS': return 'rgba(244, 63, 94, 0.6)'   // rose
    case 'SUPPORTS':    return 'rgba(16, 185, 129, 0.4)'   // green
    case 'RELATES_TO':  return 'rgba(139, 92, 246, 0.4)'   // violet
    default:            return 'rgba(71, 85, 105, 0.2)'     // dim
  }
}

function getEdgeWidth(edge: { type?: string }): number {
  return edge.type === 'CONTRADICTS' ? 1.8 : 0.8
}

// ─── Legend ──────────────────────────────────────────────────────────────────

function Legend() {
  const nodeItems = [
    { color: '#3b82f6', label: 'Paper' },
    { color: '#10b981', label: 'Claim (High)' },
    { color: '#f59e0b', label: 'Claim (Med)' },
    { color: '#f43f5e', label: 'Claim (Low)' },
    { color: '#8b5cf6', label: 'Gap' },
  ]
  const edgeItems = [
    { color: '#f43f5e', label: 'Contradicts', style: 'solid' },
    { color: '#475569', label: 'Extracted From', style: 'dashed' },
  ]

  return (
    <div className="absolute bottom-4 left-4 z-10 rounded-xl border border-[var(--axion-border-subtle)] axion-glass p-3">
      <p className="mb-2 text-[10px] font-medium uppercase tracking-wider text-[#475569]">Nodes</p>
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {nodeItems.map((item) => (
          <div key={item.label} className="flex items-center gap-1.5">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: item.color }}
            />
            <span className="text-[10px] text-[#94a3b8]">{item.label}</span>
          </div>
        ))}
      </div>
      <p className="mb-1 mt-2 text-[10px] font-medium uppercase tracking-wider text-[#475569]">Edges</p>
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {edgeItems.map((item) => (
          <div key={item.label} className="flex items-center gap-1.5">
            <span
              className="inline-block h-0.5 w-4"
              style={{
                backgroundColor: item.color,
                borderStyle: item.style === 'dashed' ? 'dashed' : 'solid',
              }}
            />
            <span className="text-[10px] text-[#94a3b8]">{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Main Component ──────────────────────────────────────────────────────────

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

  return (
    <div ref={containerRef} className="relative h-full w-full bg-[#020408]">
      {/* Floating Controls */}
      <div className="absolute right-4 top-4 z-10 flex items-center gap-2 rounded-xl border border-[var(--axion-border-subtle)] axion-glass px-3 py-2">
        {/* Node count */}
        {graphData && (
          <Badge
            variant="outline"
            className="border-[var(--axion-border-subtle)] bg-transparent text-[10px] text-[#475569] font-mono"
          >
            {graphData.nodes.length} nodes · {graphData.edges.length} edges
          </Badge>
        )}

        <div className="h-4 w-px bg-[var(--axion-border-subtle)]" />

        {/* Claim limit slider */}
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-[#475569]">Claims:</span>
          <div className="w-20">
            <Slider
              defaultValue={[claimLimit]}
              min={25}
              max={200}
              step={25}
              onValueCommit={(val: number[]) => setClaimLimit(val[0])}
            />
          </div>
          <span className="w-6 text-right font-mono text-[10px] text-[#94a3b8] tabular-nums">
            {claimLimit}
          </span>
        </div>

        <div className="h-4 w-px bg-[var(--axion-border-subtle)]" />

        {/* Zoom controls */}
        <div className="flex items-center gap-0.5">
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-[#475569] hover:text-[#f0f6ff] hover:bg-[rgba(59,130,246,0.08)]"
            onClick={handleZoomIn}
          >
            <ZoomIn className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-[#475569] hover:text-[#f0f6ff] hover:bg-[rgba(59,130,246,0.08)]"
            onClick={handleZoomOut}
          >
            <ZoomOut className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-[#475569] hover:text-[#f0f6ff] hover:bg-[rgba(59,130,246,0.08)]"
            onClick={handleZoomToFit}
          >
            <Maximize2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="rounded-xl border border-[#f43f5e]/20 bg-[#f43f5e]/5 p-4">
            <p className="text-sm text-[#f43f5e]">
              Failed to load graph data. Is the API running?
            </p>
          </div>
        </div>
      )}

      {/* Graph canvas */}
      {isLoading ? (
        <div className="flex h-full items-center justify-center">
          <div className="space-y-3 text-center">
            <Loader2 className="mx-auto h-8 w-8 animate-spin text-[#3b82f6]" />
            <p className="text-sm text-[#475569]">Loading graph data…</p>
          </div>
        </div>
      ) : graphData && graphData.nodes.length > 0 ? (
        <>
          <ForceGraph2D
            ref={graphRef}
            graphData={fgData}
            width={dimensions.width}
            height={dimensions.height}
            backgroundColor="#020408"
            nodeRelSize={1}
            nodeVal={(node) => getNodeSize(node as GraphNode) ** 2}
            nodeColor={(node) => getNodeColor(node as GraphNode)}
            nodeLabel=""
            linkColor={(link) => getEdgeColor(link as { type?: string })}
            linkWidth={(link) => getEdgeWidth(link as { type?: string })}
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
              const color = getNodeColor(gn)
              const x = gn.x ?? 0
              const y = gn.y ?? 0

              // Glow effect
              if (gn.type === 'paper' || gn.type === 'gap') {
                ctx.beginPath()
                ctx.arc(x, y, size + 3, 0, 2 * Math.PI)
                ctx.fillStyle = `${color}15`
                ctx.fill()
                ctx.beginPath()
                ctx.arc(x, y, size + 1.5, 0, 2 * Math.PI)
                ctx.fillStyle = `${color}25`
                ctx.fill()
              }

              // Main circle
              ctx.beginPath()
              ctx.arc(x, y, size, 0, 2 * Math.PI)
              ctx.fillStyle = color
              ctx.fill()

              // Border
              ctx.strokeStyle = `${color}66`
              ctx.lineWidth = 0.3
              ctx.stroke()

              // Label at high zoom
              if (globalScale > 2.5 && gn.label) {
                ctx.font = `${Math.max(2, 10 / globalScale)}px Inter, sans-serif`
                ctx.textAlign = 'center'
                ctx.textBaseline = 'top'
                ctx.fillStyle = '#94a3b8'
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
          <div className="text-center">
            <Network className="mx-auto h-10 w-10 text-[#334155]" />
            <p className="mt-3 text-sm text-[#94a3b8]">
              No graph data available
            </p>
            <p className="mt-1 text-xs text-[#475569]">
              Ingest some papers first to populate the knowledge graph
            </p>
          </div>
        </div>
      )}

      {/* Hover tooltip */}
      {hoveredNode && (
        <div className="absolute right-4 top-16 z-20 max-w-xs rounded-xl border border-[var(--axion-border-subtle)] axion-glass-strong p-3 animate-fade-up">
          <div className="flex items-center gap-2">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: getNodeColor(hoveredNode) }}
            />
            <Badge
              variant="outline"
              className="border-[var(--axion-border-subtle)] bg-transparent text-[10px] uppercase text-[#475569]"
            >
              {hoveredNode.type}
            </Badge>
          </div>
          <p className="mt-2 text-sm text-[#f0f6ff] leading-snug">
            {hoveredNode.label}
          </p>
          {hoveredNode.confidence !== undefined && (
            <p className="mt-1 text-xs text-[#475569]">
              Confidence:{' '}
              <span className="font-mono text-[#94a3b8] tabular-nums">
                {Math.round(hoveredNode.confidence * 100)}%
              </span>
            </p>
          )}
        </div>
      )}
    </div>
  )
}
