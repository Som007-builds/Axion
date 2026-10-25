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
  evidence_span?: string
  subject?: string
  predicate?: string
  object_val?: string
  metric?: string
  direction?: string
  conditions?: string
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
  corpus_total: number
  shown: number
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

export type GapSource =
  | 'cluster'
  | 'future_work'
  | 'legacy_import'
  | 'unknown'

export interface GapClaimRef {
  id: string
  text: string
  section?: string | null
  confidence?: number | null
  arxiv_id?: string | null
  paper_title?: string | null
}

export interface Gap {
  id: string
  text: string
  source: GapSource
  source_raw?: string | null
  source_label: string
  source_description: string
  related_claims: string[]
  related_claim_details: GapClaimRef[]
  confidence?: number | null
}

export interface GapsResponse {
  total: number
  corpus_total: number
  source_counts: Record<GapSource | 'all', number>
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
  /** @deprecated Coarse display bucket; use the raw model-reported label. */
  confidence: number
  confidence_label?: 'high' | 'medium' | 'low' | 'unknown'
  sources: string[]
  source_count?: number
  claim_count?: number
  contradiction_count?: number
  gap_count?: number
}

// ─── Background jobs ──────────────────────────────────────────────────────────
// Queries and ingestion run as queued jobs: POST returns a job id, and the
// client polls GET /api/jobs/{id} until the status is terminal.

export type JobStatus = 'queued' | 'running' | 'completed' | 'failed'

export interface JobSubmitResponse {
  job_id: string
  status: JobStatus
  /** 'rq' when a worker will pick the job up, 'inline' in single-process dev. */
  backend?: 'rq' | 'inline'
}

export interface JobRecord<T> {
  id: string
  kind: string
  status: JobStatus
  created_at: number
  started_at: number | null
  finished_at: number | null
  result: T | null
  error: string | null
  backend?: 'rq' | 'inline'
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
  supports: number
  contradictions: number
  arxiv_id?: string | null
  paper_title?: string | null
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
  start_year: number | null
  end_year: number | null
  resolved: boolean
  status: 'active' | 'resolved' | 'fading' | 'unknown'
  resolution?: string
  key_claims: string[]
}

export interface DisputeTimeline {
  topic: string
  disputes: Dispute[]
  summary?: string
  candidate_claim_count?: number
  contradiction_count?: number
  year_start?: number
  year_end?: number
}

export interface GraphNode {
  id: string
  type: 'paper' | 'claim' | 'gap'
  label: string
  text?: string
  confidence?: number
  year?: number
  arxiv_id?: string
  paper_title?: string
  section?: string
  source?: string
}

export interface GraphEdge {
  source: string
  target: string
  type: 'EXTRACTED_FROM' | 'CONTRADICTS' | 'SUPPORTS' | 'RELATED_TO'
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface CustomIngestionProgress {
  // 'queued' is reported while a job is waiting for the worker to claim it.
  status:
    | 'idle'
    | 'queued'
    | 'searching'
    | 'processing'
    | 'contradiction'
    | 'confidence'
    | 'completed'
    | 'failed'
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
