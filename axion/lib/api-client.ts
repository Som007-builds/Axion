// Axion API Client - communicates with FastAPI backend

import type {
  GraphStats,
  ContradictionsResponse,
  Experiment,
  GapsResponse,
  CoordinatorOutput,
  IngestionStatus,
  ConfidenceDistribution,
  ChangedClaim,
  TemporalEvolution,
  DisputeTimeline,
  GraphData,
  CustomIngestionProgress,
  JobRecord,
  JobStatus,
  JobSubmitResponse,
} from '@/types/axion'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${endpoint}`
  
  let response: Response
  try {
    response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    })
  } catch (err) {
    throw new ApiError(0, err instanceof Error ? err.message : 'Network error')
  }

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error')
    throw new ApiError(response.status, errorText)
  }

  return response.json()
}

// Write/compute calls go through the Next.js server-side proxy, which attaches
// the backend API key. The key is therefore never present in the client bundle.
// Job polling (GET /api/jobs/{id}) goes through the same proxy because job
// results are credentialled too.
async function proxyFetch<T>(
  endpoint: string,
  options: { method: 'GET' | 'POST'; body?: Record<string, unknown> }
): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api/backend${endpoint}`, {
      method: options.method,
      headers: { 'Content-Type': 'application/json' },
      body: options.body ? JSON.stringify(options.body) : undefined,
      cache: 'no-store',
    })
  } catch (err) {
    throw new ApiError(0, err instanceof Error ? err.message : 'Network error')
  }

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error')
    throw new ApiError(response.status, errorText)
  }

  return response.json()
}

async function fetchViaProxy<T>(endpoint: string, body?: Record<string, unknown>): Promise<T> {
  return proxyFetch<T>(endpoint, { method: 'POST', body })
}

async function fetchViaProxyGet<T>(endpoint: string): Promise<T> {
  return proxyFetch<T>(endpoint, { method: 'GET' })
}

// Stats
export async function getStats(): Promise<GraphStats> {
  return fetchApi<GraphStats>('/api/stats')
}

// Contradictions
export async function getContradictions(
  minConfidence = 0
): Promise<ContradictionsResponse> {
  return fetchApi<ContradictionsResponse>(
    `/api/contradictions?min_confidence=${minConfidence}`
  )
}

// Experiments
export async function getExperiment(
  contradictionId: string
): Promise<Experiment | null> {
  try {
    return await fetchApi<Experiment>(`/api/experiments/${contradictionId}`)
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null
    }
    throw error
  }
}

export async function designExperiment(
  contradictionId: string
): Promise<Experiment> {
  return fetchViaProxy<Experiment>(`/experiments/${contradictionId}/design`)
}

// Research Gaps
export async function getGaps(source?: 'semantic' | 'llm_synthesized'): Promise<GapsResponse> {
  const params = source ? `?source=${source}` : ''
  return fetchApi<GapsResponse>(`/api/gaps${params}`)
}

// ─── Background jobs ──────────────────────────────────────────────────────────

const JOB_POLL_INTERVAL_MS = 2000
// Keep in sync with JOB_TIMEOUT_SECONDS (default 1800s) in the backend config:
// a job cannot outlive its queue timeout, so polling longer is pointless.
const JOB_POLL_TIMEOUT_MS = 30 * 60 * 1000

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** Queue a research query. Returns as soon as the job is enqueued. */
export async function submitQuery(question: string): Promise<JobSubmitResponse> {
  return fetchViaProxy<JobSubmitResponse>('/query', { question })
}

/** Current state of a queued job (status, and the result once completed). */
export async function getJob<T>(jobId: string): Promise<JobRecord<T>> {
  return fetchViaProxyGet<JobRecord<T>>(`/jobs/${jobId}`)
}

export interface WaitForJobOptions {
  /** Called on every poll with the job's current status. */
  onStatus?: (status: JobStatus, jobId: string) => void
  intervalMs?: number
  timeoutMs?: number
}

/**
 * Poll a job until it reaches a terminal state and return the finished record.
 * Throws `ApiError` if the job fails or the timeout elapses.
 */
export async function waitForJob<T>(
  jobId: string,
  options: WaitForJobOptions = {}
): Promise<JobRecord<T>> {
  const interval = options.intervalMs ?? JOB_POLL_INTERVAL_MS
  const timeout = options.timeoutMs ?? JOB_POLL_TIMEOUT_MS
  const deadline = Date.now() + timeout

  // First poll immediately: the job may already be done (inline backend).
  for (;;) {
    const job = await getJob<T>(jobId)
    options.onStatus?.(job.status, jobId)

    if (job.status === 'completed') return job
    if (job.status === 'failed') {
      throw new ApiError(500, job.error || 'Job failed')
    }
    if (Date.now() + interval > deadline) {
      throw new ApiError(504, 'The job is still running after 30 minutes.')
    }
    await delay(interval)
  }
}

// Coordinator Query
// The coordinator loop runs for minutes, so the backend queues it: submit, then
// poll until the report is ready.
export async function runQuery(
  question: string,
  options: WaitForJobOptions = {}
): Promise<CoordinatorOutput> {
  const submitted = await submitQuery(question)
  options.onStatus?.(submitted.status, submitted.job_id)

  const job = await waitForJob<CoordinatorOutput>(submitted.job_id, options)
  if (!job.result) {
    throw new ApiError(500, 'The query finished without a result.')
  }
  return job.result
}

// Temporal Analysis
export async function getEvolution(
  topic: string,
  yearStart = 2020,
  yearEnd = 2026
): Promise<TemporalEvolution> {
  return fetchApi<TemporalEvolution>(
    `/api/temporal/evolution?topic=${encodeURIComponent(topic)}&year_start=${yearStart}&year_end=${yearEnd}`
  )
}

export async function getDisputes(topic: string): Promise<DisputeTimeline> {
  return fetchApi<DisputeTimeline>(
    `/api/temporal/disputes?topic=${encodeURIComponent(topic)}`
  )
}

// Confidence Analysis
export async function getConfidenceDistribution(): Promise<ConfidenceDistribution> {
  return fetchApi<ConfidenceDistribution>('/api/confidence/distribution')
}

export async function getMostChanged(limit = 10): Promise<ChangedClaim[]> {
  return fetchApi<ChangedClaim[]>(`/api/confidence/most-changed?limit=${limit}`)
}

export async function recalculateConfidence(): Promise<{ updated: number }> {
  return fetchViaProxy<{ updated: number }>('/confidence/recalculate')
}

// Ingestion
// Both triggers are queued now: they return a job id immediately and the sheet
// follows progress via /api/ingestion/progress.
export async function triggerIngestion(): Promise<JobSubmitResponse> {
  return fetchViaProxy<JobSubmitResponse>('/ingestion/trigger')
}

export async function getIngestionStatus(): Promise<IngestionStatus> {
  return fetchApi<IngestionStatus>('/api/ingestion/status')
}

export async function runCustomIngestion(topic: string, limit: number): Promise<JobSubmitResponse> {
  return fetchViaProxy<JobSubmitResponse>('/ingestion/custom', { topic, limit })
}

export async function getIngestionProgress(): Promise<CustomIngestionProgress> {
  return fetchApi<CustomIngestionProgress>('/api/ingestion/progress')
}

// Knowledge Graph
export async function getGraphData(limitClaims = 100): Promise<GraphData> {
  return fetchApi<GraphData>(`/api/graph?limit_claims=${limitClaims}`)
}

// Health
export async function getHealth(): Promise<{ status: string }> {
  return fetchApi<{ status: string }>('/api/health')
}

// Export error class for consumers
export { ApiError }
