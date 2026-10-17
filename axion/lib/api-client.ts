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
async function fetchViaProxy<T>(
  endpoint: string,
  body?: Record<string, unknown>
): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api/backend${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
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

// Coordinator Query
export async function runQuery(question: string): Promise<CoordinatorOutput> {
  return fetchViaProxy<CoordinatorOutput>('/query', { question })
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
export async function triggerIngestion(): Promise<{ status: string }> {
  return fetchViaProxy<{ status: string }>('/ingestion/trigger')
}

export async function getIngestionStatus(): Promise<IngestionStatus> {
  return fetchApi<IngestionStatus>('/api/ingestion/status')
}

export async function runCustomIngestion(topic: string, limit: number): Promise<{ status: string }> {
  return fetchViaProxy<{ status: string }>('/ingestion/custom', { topic, limit })
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
