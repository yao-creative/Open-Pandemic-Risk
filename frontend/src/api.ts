import type {
  PipelineCountryDetailResponse,
  PipelineCountryResultsResponse,
  PipelineRunCreateResponse,
  PipelineRunStatusResponse
} from './types'

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {})
    },
    ...init
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `${response.status} ${response.statusText}`)
  }

  return (await response.json()) as T
}

export const api = {
  apiBase,
  createPipelineRun: (idempotencyKey: string) =>
    request<PipelineRunCreateResponse>('/pipeline/run', {
      method: 'POST',
      body: JSON.stringify({ idempotency_key: idempotencyKey })
    }),
  getPipelineRun: (pipelineRunId: number) =>
    request<PipelineRunStatusResponse>(`/pipeline/runs/${pipelineRunId}`),
  getLatestResults: () => request<PipelineCountryResultsResponse>('/pipeline/runs/latest/results'),
  getResults: (pipelineRunId: number) =>
    request<PipelineCountryResultsResponse>(`/pipeline/runs/${pipelineRunId}/results`),
  getCountryDetail: (pipelineRunId: number, countryCode: string) =>
    request<PipelineCountryDetailResponse>(`/pipeline/runs/${pipelineRunId}/results/${countryCode}`)
}
