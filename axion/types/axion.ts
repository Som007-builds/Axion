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
  confidence?: number | null
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
  start_year: number | null
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
