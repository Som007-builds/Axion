# AXION Frontend Handover & API Contract Specification

> **Status:** supplementary reference. The authoritative, current project
> inventory is [`PROJECT_INFO.md`](PROJECT_INFO.md); actionable work is tracked
> in [`progress.md`](progress.md). Product name: **Axion**.

This document provides a complete, read-only architectural contract and specification of the `axion/` Next.js frontend. It details the exact API endpoints, TypeScript data models, view inventories, state management behaviors, configuration settings, dependencies, known quirks, and a minimum viable swap checklist for building a drop-in frontend replacement.

---

## 1. API Contract

The frontend communicates with the FastAPI backend (default base URL: `http://localhost:8000`). All API calls are executed via `axion/lib/api-client.ts`.

### Endpoints Inventory

#### 1. Graph Statistics
- **Client Function**: `getStats()`
- **HTTP Method**: `GET`
- **Path**: `/api/stats`
- **Request Body**: None
- **Response Shape**: `GraphStats`
  ```json
  {
    "papers": 48,
    "claims": 2389,
    "contradictions": 224,
    "gaps": 30,
    "experiments": 12
  }
  ```
- **Backend Status**: Matched with `api/main.py` `@app.get("/api/stats")`.

---

#### 2. Claims List
- **Client Function**: `getClaims(limit = 50, offset = 0)`
- **HTTP Method**: `GET`
- **Path**: `/api/claims?limit={limit}&offset={offset}`
- **Request Body**: None
- **Response Shape**: `ClaimsResponse`
  ```json
  {
    "total": 2389,
    "claims": [
      {
        "id": "4:17c98ca7...",
        "text": "Claim statement text",
        "section": "Abstract",
        "confidence": 0.85,
        "base_confidence": 0.85,
        "arxiv_id": "2201.11903",
        "paper_year": 2022,
        "paper_title": "Chain-of-Thought Prompting..."
      }
    ]
  }
  ```
- **Backend Status**: Matched with `api/main.py` `@app.get("/api/claims")`.
- **Note**: `api/main.py` returns extra fields (`base_confidence`, `evidence_span`, `subject`, `metric`, `direction`) on claim objects which are present in JSON response but not fully typed in `axion/types/axion.ts`.

---

#### 3. Contradictions List
- **Client Function**: `getContradictions(minConfidence = 0)`
- **HTTP Method**: `GET`
- **Path**: `/api/contradictions?min_confidence={minConfidence}`
- **Request Body**: None
- **Response Shape**: `ContradictionsResponse`
  ```json
  {
    "total": 224,
    "contradictions": [
      {
        "id": "rel_id_123",
        "claim_a": {
          "id": "claim_a_id",
          "text": "Claim text A",
          "section": "Unknown",
          "confidence": 0.9,
          "arxiv_id": ""
        },
        "claim_b": {
          "id": "claim_b_id",
          "text": "Claim text B",
          "section": "Unknown",
          "confidence": 0.9,
          "arxiv_id": ""
        },
        "paper_a": "2201.11903",
        "paper_b": "2205.10625",
        "explanation": "Conflict explanation narrative",
        "confidence": 0.9,
        "has_experiment": true
      }
    ]
  }
  ```
- **Backend Status**: Matched with `api/main.py` `@app.get("/api/contradictions")`.

---

#### 4. Get Designed Experiment
- **Client Function**: `getExperiment(contradictionId: string)`
- **HTTP Method**: `GET`
- **Path**: `/api/experiments/{contradiction_id}`
- **Request Body**: None
- **Response Shape**: `Experiment` or `null` (HTTP 404 returns `null`)
  ```json
  {
    "contradiction_id": "rel_123",
    "title": "Experimental Validation Plan",
    "hypothesis_a": "Hypothesis A explanation",
    "hypothesis_b": "Hypothesis B explanation",
    "procedure": "1. Step one\n2. Step two",
    "dataset": "GSM8K Benchmark",
    "duration": "24 hours",
    "cost": "$15.00",
    "decision_rule": "Accept A if accuracy > 85%",
    "caveats": ["Sample size limitation"],
    "design_confidence": 0.88,
    "metric": "Accuracy Score"
  }
  ```
- **Backend Status**: Matched with `api/main.py` `@app.get("/api/experiments/{contradiction_id}")`.

---

#### 5. Design Experiment On-Demand
- **Client Function**: `designExperiment(contradictionId: string)`
- **HTTP Method**: `POST`
- **Path**: `/api/experiments/{contradiction_id}/design`
- **Request Body**: None
- **Rate Limit**: 5 requests / minute
- **Response Shape**: `Experiment`
- **Backend Status**: Matched with `api/main.py` `@app.post("/api/experiments/{contradiction_id}/design")`.

---

#### 6. Research Gaps List
- **Client Function**: `getGaps(source?: 'semantic' | 'llm_synthesized')`
- **HTTP Method**: `GET`
- **Path**: `/api/gaps` or `/api/gaps?source={source}`
- **Request Body**: None
- **Response Shape**: `GapsResponse`
  ```json
  {
    "total": 30,
    "gaps": [
      {
        "id": "gap_123",
        "text": "Unexplored synthesis between RAG and agent memory",
        "source": "llm_synthesized",
        "related_claims": ["claim_1", "claim_2"],
        "confidence": 0.8
      }
    ]
  }
  ```
- **Backend Status**: Matched with `api/main.py` `@app.get("/api/gaps")`.

---

#### 7. Coordinator Research Query
- **Client Function**: `runQuery(question: string)`
- **HTTP Method**: `POST`
- **Path**: `/api/query`
- **Request Body**: `{ "question": "string" }`
- **Rate Limit**: 10 requests / minute
- **Response Shape**: `CoordinatorOutput`
  ```json
  {
    "report": "# Executive Summary\n...",
    "raw": "{\"consensus\": [...], \"disputed\": [...], \"missing\": [...], \"recommended_experiments\": [...], \"confidence_in_answer\": \"high\", \"confidence_reason\": \"...\"}",
    "iterations": 2,
    "plan": ["Subquery 1", "Subquery 2"],
    "reflection_log": [
      {
        "step": 1,
        "action": "Iteration 1 reflection",
        "observation": "Found 12 claims",
        "reasoning": "Context marked sufficient"
      }
    ],
    "confidence": 0.9,
    "sources": ["2201.11903", "2205.10625"]
  }
  ```
- **Backend Status**: Matched with `api/main.py` `@app.post("/api/query")`. FastAPI validates that `question` length <= 500 characters.

---

#### 8. Temporal Evolution Analysis
- **Client Function**: `getEvolution(topic: string, yearStart = 2020, yearEnd = 2026)`
- **HTTP Method**: `GET`
- **Path**: `/api/temporal/evolution?topic={topic}&year_start={yearStart}&year_end={yearEnd}`
- **Request Body**: None
- **Response Shape**: `TemporalEvolution`
  ```json
  {
    "topic": "transformer scaling laws",
    "yearly_positions": [
      {
        "year": 2020,
        "position": "Initial power-law scaling proposed",
        "confidence": 0.85,
        "key_papers": ["2001.08361"]
      }
    ],
    "narrative": "Consensus shifted from power laws to compute-optimal scaling",
    "current_status": "Chinchilla optimal scaling widely adopted"
  }
  ```
- **Backend Status**: Matched with `api/main.py` `@app.get("/api/temporal/evolution")`.

---

#### 9. Dispute Timeline
- **Client Function**: `getDisputes(topic: string)`
- **HTTP Method**: `GET`
- **Path**: `/api/temporal/disputes?topic={topic}`
- **Request Body**: None
- **Response Shape**: `DisputeTimeline`
  ```json
  {
    "topic": "transformer scaling laws",
    "disputes": [
      {
        "id": "disp_1",
        "topic": "Dispute over optimal dataset size vs parameter count",
        "start_year": 2020,
        "end_year": 2022,
        "resolved": false,
        "key_claims": ["Kaplan et al. claim", "Hoffmann et al. claim"]
      }
    ]
  }
  ```
- **Backend Status**: Matched with `api/main.py` `@app.get("/api/temporal/disputes")`.

---

#### 10. Confidence Distribution Stats
- **Client Function**: `getConfidenceDistribution()`
- **HTTP Method**: `GET`
- **Path**: `/api/confidence/distribution`
- **Request Body**: None
- **Response Shape**: `ConfidenceDistribution`
  ```json
  {
    "total": 2389,
    "average": 0.76,
    "high": 1800,
    "medium": 450,
    "low": 139
  }
  ```
- **Backend Status**: Matched with `api/main.py` `@app.get("/api/confidence/distribution")`.

---

#### 11. Most Changed Claims
- **Client Function**: `getMostChanged(limit = 10)`
- **HTTP Method**: `GET`
- **Path**: `/api/confidence/most-changed?limit={limit}`
- **Request Body**: None
- **Response Shape**: `ChangedClaim[]`
  ```json
  [
    {
      "claim_id": "claim_123",
      "claim_text": "Chain-of-thought prompting improves reasoning",
      "base_confidence": 0.70,
      "current_confidence": 0.88,
      "delta": 0.18,
      "reason": "12 supports, 1 contradiction"
    }
  ]
  ```
- **Backend Status**: Matched with `api/main.py` `@app.get("/api/confidence/most-changed")`.

---

#### 12. Recalculate Confidence
- **Client Function**: `recalculateConfidence()`
- **HTTP Method**: `POST`
- **Path**: `/api/confidence/recalculate`
- **Request Body**: None
- **Rate Limit**: 2 requests / minute
- **Response Shape**: `{ "updated": 2389 }`
- **Backend Status**: Matched with `api/main.py` `@app.post("/api/confidence/recalculate")`.

---

#### 13. Trigger Background Ingestion
- **Client Function**: `triggerIngestion(secret?: string)`
- **HTTP Method**: `POST`
- **Path**: `/api/ingestion/trigger`
- **Headers**: `X-Trigger-Secret: <secret>` (if `TRIGGER_SECRET` environment variable or passed secret is set)
- **Rate Limit**: 2 requests / minute
- **Response Shape**: `{ "status": "ingestion started in background" }`
- **Backend Status**: Matched with `api/main.py` `@app.post("/api/ingestion/trigger")`.

---

#### 14. Ingestion Summary Status
- **Client Function**: `getIngestionStatus()`
- **HTTP Method**: `GET`
- **Path**: `/api/ingestion/status`
- **Request Body**: None
- **Response Shape**: `IngestionStatus`
  ```json
  {
    "new_papers": 0,
    "new_claims": 0,
    "last_run": "2026-08-09T18:30:00Z",
    "running": false,
    "error": null
  }
  ```
- **Backend Status**: Matched with `api/main.py` `@app.get("/api/ingestion/status")`.

---

#### 15. Custom Topic Ingestion
- **Client Function**: `runCustomIngestion(topic: string, limit: number, secret?: string)`
- **HTTP Method**: `POST`
- **Path**: `/api/ingestion/custom`
- **Headers**: `X-Trigger-Secret: <secret>` (if `TRIGGER_SECRET` environment variable or passed secret is set)
- **Request Body**: `{ "topic": "direct preference optimization", "limit": 5 }`
- **Rate Limit**: 5 requests / minute
- **Response Shape**: `{ "status": "custom ingestion started in background" }`
- **Backend Status**: Matched with `api/main.py` `@app.post("/api/ingestion/custom")`.

---

#### 16. Custom Ingestion Real-time Progress
- **Client Function**: `getIngestionProgress()`
- **HTTP Method**: `GET`
- **Path**: `/api/ingestion/progress`
- **Request Body**: None
- **Response Shape**: `CustomIngestionProgress`
  ```json
  {
    "status": "processing",
    "topic": "direct preference optimization",
    "limit": 5,
    "current_index": 2,
    "current_paper_id": "2305.18290",
    "current_paper_title": "Direct Preference Optimization...",
    "current_step": "Extracting claims from Section 3",
    "papers_added": 2,
    "claims_added": 45,
    "contradictions_found": 3,
    "percent": 40,
    "remaining_seconds": 90,
    "error_message": "",
    "logs": ["[18:42:01] Processing paper 2305.18290..."],
    "running": true
  }
  ```
- **Backend Status**: Matched with `api/main.py` `@app.get("/api/ingestion/progress")`.

---

#### 17. Knowledge Graph Data
- **Client Function**: `getGraphData(limitClaims = 100)`
- **HTTP Method**: `GET`
- **Path**: `/api/graph?limit_claims={limitClaims}`
- **Request Body**: None
- **Response Shape**: `GraphData`
  ```json
  {
    "nodes": [
      { "id": "paper_2201.11903", "label": "Chain-of-Thought...", "type": "paper", "year": 2024 },
      { "id": "claim_123", "label": "CoT improves...", "type": "claim", "confidence": 0.85 },
      { "id": "gap_456", "label": "Unexplored area...", "type": "gap" }
    ],
    "edges": [
      { "source": "claim_123", "target": "paper_2201.11903", "type": "EXTRACTED_FROM" },
      { "source": "claim_123", "target": "claim_789", "type": "CONTRADICTS" }
    ]
  }
  ```
- **Backend Status**: Matched with `api/main.py` `@app.get("/api/graph")`.

---

#### 18. Health Check
- **Client Function**: `getHealth()`
- **HTTP Method**: `GET`
- **Path**: `/api/health`
- **Request Body**: None
- **Response Shape**: `{ "status": "ok", "neo4j": "connected", "chromadb": "connected", "claims": 2389 }`
- **Backend Status**: Matched with `api/main.py` `@app.get("/api/health")`.

---

### Backend Endpoints Not Currently Called by `axion/lib/api-client.ts`
1. `GET /api/claims/{claim_id}/provenance` — Phase 7 provenance endpoint returning structured entity triples, evidence span, and paper metadata for a claim.
2. `GET /api/metrics` — Phase 9 observability endpoint returning aggregated metrics for LLM calls, ingestion runs, vector writes, and LLM cache hit rates.

### Authentication & Headers Summary
- **No global auth tokens** (JWT/OAuth) are enforced on general read/query APIs.
- **`X-Trigger-Secret` Header**: Enforced on `POST /api/ingestion/trigger` and `POST /api/ingestion/custom` when `TRIGGER_SECRET` environment variable is configured in backend `.env`.
- **CORS Configuration**: Allowed origins configured in backend `config.py` (`ALLOWED_ORIGINS`, including `http://localhost:3000` and `http://localhost:5173`).

---

## 2. TypeScript Types / Data Shapes

Below is the verbatim dump of `axion/types/axion.ts`. Every new frontend MUST produce and consume data adhering strictly to these interface shapes.

```typescript
// Axion API Types - matching FastAPI response models

export interface GraphStats {
  papers: number
  claims: number
  contradictions: number
  gaps: number
  experiments: number
}

export interface Claim {
  id: string
  text: string
  section: string
  confidence: number
  arxiv_id: string
  paper_year: number
  paper_title?: string
}

export interface ClaimsResponse {
  total: number
  claims: Claim[]
}

export interface Contradiction {
  id: string
  claim_a: Claim
  claim_b: Claim
  paper_a: string
  paper_b: string
  explanation: string
  confidence: number
  has_experiment?: boolean
}

export interface ContradictionsResponse {
  total: number
  contradictions: Contradiction[]
}

export interface Experiment {
  contradiction_id: string
  title: string
  hypothesis_a: string
  hypothesis_b: string
  procedure: string
  dataset: string
  duration: string
  cost: string
  decision_rule: string
  caveats: string[]
  design_confidence: number
  metric?: string
}

export interface Gap {
  id: string
  text: string
  source: 'semantic' | 'llm_synthesized'
  related_claims: string[]
  confidence?: number
}

export interface GapsResponse {
  total: number
  gaps: Gap[]
}

export interface ReflectionStep {
  step: number
  observation: string
  reasoning: string
  action: string
}

export interface CoordinatorOutput {
  report: string
  raw: string
  iterations: number
  plan: string[]
  reflection_log: ReflectionStep[]
  confidence: number
  sources: string[]
}

export interface IngestionStatus {
  new_papers: number
  new_claims: number
  last_run: string | null
  running: boolean
  error?: string
}

export interface ConfidenceDistribution {
  total: number
  average: number
  high: number // > 0.8
  medium: number // 0.5 - 0.8
  low: number // < 0.5
}

export interface ChangedClaim {
  claim_id: string
  claim_text: string
  base_confidence: number
  current_confidence: number
  delta: number
  reason: string
}

export interface YearlyPosition {
  year: number
  position: string
  confidence: number
  key_papers: string[]
}

export interface TemporalEvolution {
  topic: string
  yearly_positions: YearlyPosition[]
  narrative: string
  current_status: string
}

export interface Dispute {
  id: string
  topic: string
  start_year: number
  end_year: number | null
  resolved: boolean
  resolution?: string
  key_claims: string[]
}

export interface DisputeTimeline {
  topic: string
  disputes: Dispute[]
}

export interface GraphNode {
  id: string
  type: 'paper' | 'claim' | 'gap'
  label: string
  confidence?: number
  year?: number
}

export interface GraphEdge {
  source: string
  target: string
  type: 'EXTRACTED_FROM' | 'CONTRADICTS' | 'SUPPORTS' | 'RELATES_TO'
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface CustomIngestionProgress {
  status: 'idle' | 'searching' | 'processing' | 'contradiction' | 'confidence' | 'completed' | 'failed'
  topic: string
  limit: number
  current_index: number
  current_paper_id: string
  current_paper_title: string
  current_step: string
  papers_added: number
  claims_added: number
  contradictions_found: number
  percent: number
  remaining_seconds: number
  error_message: string
  logs: string[]
  running: boolean
}
```

---

## 3. Views / Pages Inventory

View switching is driven by client-side state in `axion/app/page.tsx` (`activeView: AxionView` = `'query' | 'knowledge-graph' | 'contradictions' | 'gaps' | 'timeline' | 'evolution'`). Keyboard shortcuts `1` through `6` switch between views.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ NavRail (Sidebar)   │ Header (CommandBar + View Title + DashboardStats)                │
│ 1. Research         │──────────────────────────────────────────────────────────────────│
│ 2. Knowledge Graph  │ Active View Content Area:                                        │
│ 3. Contradictions   │   - QueryPanel / KnowledgeGraph / ContradictionList /            │
│ 4. Research Gaps    │     GapList / TimelineView / GraphEvolution                      │
│ 5. Timeline         │──────────────────────────────────────────────────────────────────│
│ 6. Graph Evolution  │ IngestionStatus (Slide-over Sheet Drawer)                        │
│ [Ingest Papers]     │──────────────────────────────────────────────────────────────────│
│ [System Online]     │ StatusBar (Footer with Neo4j live connection indicator & counts) │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### Component Details

#### 1. `query-panel.tsx` (Research Intelligence View)
- **Data Source**: `runQuery(question)` -> `POST /api/query`.
- **Displays**:
  - Research query textarea input + execute button.
  - Multi-step loading spinner & progress indicator.
  - Overall answer confidence badge with color-coding (High: green `≥80%`, Medium: amber `50-80%`, Low: rose `<50%`).
  - Executed sub-query plan steps (`PlanSteps` collapsible).
  - Reflection reasoning log (`ReflectionLog` collapsible).
  - Rendered Markdown report output using `react-markdown` with custom citation chips linking to ArXiv (`https://arxiv.org/abs/{id}`).
  - Structured cards for Consensus points, Disputed positions (Side-by-side Position A vs Position B with ArXiv citations), Research Gaps (`missing`), Recommended Experiments, and Sources list.
- **Client-Side State**:
  - Local query history sidebar stored in `localStorage` keys `axion_query_history` and `axion-query-history`.
  - Supports selecting, deleting, and auto-submitting queries from history or top CommandBar.
- **UI Behavior**: Auto-submits when triggered via CommandBar; renders custom Markdown citation links.

#### 2. `knowledge-graph.tsx` (Knowledge Graph View)
- **Data Source**: `getGraphData(claimLimit)` -> `GET /api/graph?limit_claims={claimLimit}` using SWR.
- **Displays**:
  - Interactive 2D Force Graph rendered via dynamic SSR-disabled import of `react-force-graph-2d`.
  - Node types: `paper` (blue, size 6, glow), `claim` (green/amber/red based on confidence, size 4), `gap` (violet, size 5, glow).
  - Edge types: `CONTRADICTS` (rose, width 1.8), `EXTRACTED_FROM` (dashed/dim, width 0.8), `SUPPORTS` (green), `RELATES_TO` (violet).
  - Interactive floating controls: Claim count slider (25 to 200), zoom in (+40%), zoom out (-40%), zoom to fit.
  - Node hover cards showing node label, type badge, and confidence percentage.
  - Color-coded visual legend at bottom left.
- **Client-Side State**: Responsive container width/height tracking, slider state (`claimLimit`), hovered node state.

#### 3. `contradiction-list.tsx` (Contradictions View)
- **Data Source**: `getContradictions(minConfidence)` -> `GET /api/contradictions?min_confidence={minConfidence}` using SWR (auto-refreshes every 60s).
- **Displays**:
  - Filter slider for minimum confidence (0% to 100%, step 5%).
  - List of detected contradiction cards with confidence badges and "Has experiment" indicator.
  - Expandable accordion detail showing Claim A (Paper A ID, Section, Confidence) VS Claim B (Paper B ID, Section, Confidence) side-by-side.
  - Embedded `ExperimentCard` component to view or design an experiment on demand.
- **Client-Side State**: Accordion expansion state per card, `minConfidence` filter state.

#### 4. `gap-list.tsx` (Research Gaps View)
- **Data Source**: `getGaps(sourceFilter)` -> `GET /api/gaps?source={source}` using SWR (auto-refreshes every 60s).
- **Displays**:
  - Filter tab buttons: "All", "Semantic" (blue border), "LLM Synthesized" (violet border).
  - List of gap cards showing source badge, gap description text, confidence, and pill badges for related claim IDs.
- **Client-Side State**: `sourceFilter` selection ('all' | 'semantic' | 'llm_synthesized').

#### 5. `timeline-view.tsx` (Timeline View)
- **Data Source**: `getEvolution(topic, yearStart, yearEnd)` and `getDisputes(topic)` via `Promise.all` on user search submit.
- **Displays**:
  - Topic search input + Year range slider (2015 to 2026).
  - Narrative summary & current status box.
  - Vertical timeline rail of `YearlyPositionCard` items (year bubble, confidence indicator, position description, key paper badges).
  - `DisputeCard` list displaying start/end years, ongoing vs resolved badge, dispute explanation, resolution text, and key claims.
- **Client-Side State**: `topic`, `yearRange`, loading state, result states for evolution and disputes.

#### 6. `graph-evolution.tsx` (Graph Evolution View)
- **Data Source**: `getConfidenceDistribution()`, `getMostChanged(10)`, and `recalculateConfidence()` using SWR (auto-refreshes every 60s).
- **Displays**:
  - Overall confidence distribution progress bars: High (>80%, green), Medium (50-80%, amber), Low (<50%, rose).
  - Total claim count & average confidence stats.
  - "Most Changed Claims" feed displaying delta percentage (e.g. `+18.0%` or `-5.2%`), base confidence -> current confidence transition (`70% -> 88%`), claim text, and reason badge (`12 supports, 1 contradiction`).
  - "Recalculate" action button to invoke `/api/confidence/recalculate` and refresh SWR cache.
- **Client-Side State**: Recalculating loading state.

#### 7. `ingestion-status.tsx` (Ingestion Slide-over Sheet)
- **Data Source**: `getIngestionStatus()`, `runCustomIngestion(topic, limit)`, `getIngestionProgress()`, and `triggerIngestion()`.
- **Displays**:
  - Slide-over drawer sheet triggered from NavRail "Ingest Papers" button.
  - Custom topic ingestion form (Topic input + Paper limit 1 to 20).
  - Quick trigger button for default background cron job ingest.
  - Real-time progress view when pipeline is active: Status headline, percentage bar, estimated time remaining timer (`formatDuration`), paper/claim/conflict counters, active paper card, and terminal log window with auto-scrolling log lines.
  - Pipeline completion / failure banner with "Trigger New Ingestion" reset button.
- **Client-Side State**: Polling state (polls `/api/ingestion/progress` every 2s when running), form inputs, drawer open state.

#### 8. `dashboard-stats.tsx` (Header Stats Bar)
- **Data Source**: `getStats()` -> `GET /api/stats` using SWR (auto-refreshes every 60s).
- **Displays**: Compact header metrics for Papers, Claims, Contradictions, and Gaps. Displays "API offline" warning if endpoint errors out.

---

## 4. Environment & Config

### Environment Variables Read by Frontend

| Environment Variable | Description | Default / Fallback |
|:---|:---|:---|
| `NEXT_PUBLIC_API_URL` | Base HTTP URL for FastAPI backend | `http://localhost:8000` |
| `NEXT_PUBLIC_TRIGGER_SECRET` | Secret key sent in `X-Trigger-Secret` header for ingestion trigger APIs | `undefined` |
| `NODE_ENV` | Environment flag (`production` enables `@vercel/analytics`) | `development` |

### Base URL Configuration Mechanics
- Defined in `axion/lib/api-client.ts`:
  ```typescript
  const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
  ```
- All fetch calls append relative endpoint paths to `${API_BASE}` (e.g. `${API_BASE}/api/stats`).

### Next.js Configuration (`axion/next.config.mjs`)
- `typescript.ignoreBuildErrors: true`
- `images.unoptimized: true`

---

## 5. Dependencies Worth Knowing

Key functional packages declared in `axion/package.json` that a new frontend would need to replicate capabilities:

### Core Framework & Routing
- `next`: `16.2.6` (React 19 / App Router framework)
- `react` / `react-dom`: `^19`

### Data Fetching & State
- `swr`: `^2.4.1` (Stale-While-Revalidate data fetching, auto-revalidation, and cache mutation)

### Visualization & Graph Rendering
- `react-force-graph-2d`: `^1.29.1` (Canvas 2D HTML5 force-directed graph renderer for Neo4j knowledge graph)
- `recharts`: `2.15.0` (SVG charting library for distribution bars/charts)

### UI Components & Icons
- `lucide-react`: `^0.564.0` (Icon set across all views)
- `@radix-ui/react-*`: Radix primitives (accordion, dialog, dropdown-menu, popover, progress, slider, sheet, tabs, tooltip)
- `cmdk`: `1.1.1` (Command palette primitive for `CommandBar`)
- `vaul`: `^1.1.2` (Drawer primitive)

### Markdown & Utility Libraries
- `react-markdown`: `^10.1.0` (Renders markdown reports from coordinator `/api/query`)
- `clsx` / `tailwind-merge`: `^2.1.1` / `^3.3.1` (Tailwind class merging utility `cn()`)

---

## 6. Known Quirks / Gotchas

1. **Hydration Guard (`mounted` state)**:
   - In `axion/app/page.tsx` and `axion/components/axion/query-panel.tsx`, a `mounted` state flag (`useEffect(() => setMounted(true), [])`) is used.
   - **Reason**: Prevents Next.js SSR hydration mismatches caused by browser extensions or auto-fill tools inserting attributes (e.g. `fdprocessedid`) or accessing `localStorage` before client-side hydration completes.
   - If `mounted === false`, `AxionWorkspace` renders a dark fallback loading screen.

2. **Dual LocalStorage Keys for Query History**:
   - `query-panel.tsx` reads and writes `axion_query_history` for full query history objects (`{ id, question, timestamp, result }`).
   - It also syncs to `axion-query-history` for `CommandBar` recent queries list.
   - A replacement frontend should standardize on a single storage schema if refactoring.

3. **Dynamic Import for `react-force-graph-2d`**:
   - `react-force-graph-2d` relies on HTML5 Canvas and `window` objects. It must be dynamically imported with `{ ssr: false }` in Next.js to prevent server-side build crashes.

4. **Hardcoded Fallbacks & Dummy Values**:
   - `query-panel.tsx`: `arxivUrl` helper cleans brackets (`id.replace(/[\[\]]/g, '')`). Default paper ID fallback is `'?'`.
   - `contradiction-list.tsx`: Hardcodes claim section to `"Unknown"` when API returns incomplete claim nested objects in contradiction response.
   - `knowledge-graph.tsx`: Paper nodes use dummy `year: 2024` if missing.
   - `timeline-view.tsx`: Year slider ranges from 2015 to 2026.

5. **`api-client.ts` Error Handling**:
   - Throws custom `ApiError(status, message)` class. 
   - `getExperiment` specifically catches `ApiError` with status `404` and returns `null` instead of bubbling up an error.

---

## 7. Minimum Viable Swap Checklist

For a new frontend to be a safe, 100% drop-in replacement for `axion/`, it must satisfy the following:

- [ ] **API Endpoint Coverage**: Implement HTTP calls for all 18 backend endpoints:
  - [ ] `GET /api/stats`
  - [ ] `GET /api/claims?limit={limit}&offset={offset}`
  - [ ] `GET /api/contradictions?min_confidence={minConfidence}`
  - [ ] `GET /api/experiments/{contradiction_id}`
  - [ ] `POST /api/experiments/{contradiction_id}/design`
  - [ ] `GET /api/gaps?source={source}`
  - [ ] `POST /api/query` (Body: `{ question }`, max 500 chars)
  - [ ] `GET /api/temporal/evolution?topic={topic}&year_start={start}&year_end={end}`
  - [ ] `GET /api/temporal/disputes?topic={topic}`
  - [ ] `GET /api/confidence/distribution`
  - [ ] `GET /api/confidence/most-changed?limit={limit}`
  - [ ] `POST /api/confidence/recalculate`
  - [ ] `POST /api/ingestion/trigger` (Support `X-Trigger-Secret` header)
  - [ ] `GET /api/ingestion/status`
  - [ ] `POST /api/ingestion/custom` (Body: `{ topic, limit }`, Support `X-Trigger-Secret` header)
  - [ ] `GET /api/ingestion/progress` (Poll at 2s interval while pipeline is running)
  - [ ] `GET /api/graph?limit_claims={limitClaims}`
  - [ ] `GET /api/health`

- [ ] **Views & Navigation Capabilities**:
  - [ ] **Research Intelligence View**: Query panel with executive summary Markdown rendering, ArXiv link citations, confidence color badges, execution plan subqueries, reflection reasoning log, and local history management.
  - [ ] **Knowledge Graph View**: 2D force-directed node/edge graph rendering papers (blue), claims (color-coded by confidence), and gaps (violet) with zoom/fit controls and hover tooltips.
  - [ ] **Contradictions View**: Confidence filtering slider, side-by-side claim comparison cards, and embedded experiment design triggers.
  - [ ] **Research Gaps View**: Filtering by source ('all' | 'semantic' | 'llm_synthesized') and related claim pills.
  - [ ] **Timeline View**: Topic search, year range slider, temporal consensus narrative, yearly position cards, and dispute cards.
  - [ ] **Graph Evolution View**: High/Medium/Low confidence distribution progress bars, most changed claims feed with delta indicators, and manual recalculate button.
  - [ ] **Ingestion Slide-over Panel**: Custom topic pipeline trigger form, default cron trigger button, real-time progress bar, paper/claim/conflict counters, active paper step indicator, and auto-scrolling terminal log window.
  - [ ] **Status Bar**: Real-time Neo4j connection indicator and graph count summary.

- [ ] **Environment Variable Support**:
  - [ ] Respect `NEXT_PUBLIC_API_URL` (default: `http://localhost:8000`).
  - [ ] Respect `NEXT_PUBLIC_TRIGGER_SECRET` for ingestion endpoints.

- [ ] **Quirks & Edge Cases**:
  - [ ] Handle 404 responses gracefully for un-designed experiments (`/api/experiments/{id}`).
  - [ ] Prevent SSR hydration issues on client-side state/localStorage access.
  - [ ] Format ArXiv IDs safely into clickable URLs (`https://arxiv.org/abs/{arxiv_id}`).
