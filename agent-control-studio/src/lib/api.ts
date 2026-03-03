import type {
  AgentSummary,
  IntelData,
  ModelOption,
  PipelineData,
  RunOverrides,
  RunReport,
  SessionConfig,
  TodayData,
} from '../../shared/types'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`)
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return (await response.json()) as T
}

export function fetchAgents() {
  return fetchJson<AgentSummary[]>('/api/agents')
}

export function fetchModels() {
  return fetchJson<ModelOption[]>('/api/models')
}

export function fetchSessionConfig() {
  return fetchJson<SessionConfig>('/api/session-config')
}

export async function saveSessionConfig(config: SessionConfig) {
  const response = await fetch(`${API_BASE}/api/session-config`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(config),
  })
  if (!response.ok) {
    throw new Error(`Saving session config failed: ${response.status}`)
  }
  return (await response.json()) as SessionConfig
}

export function fetchToday() {
  return fetchJson<TodayData>('/api/files/today')
}

export function fetchIntel() {
  return fetchJson<IntelData>('/api/files/intel')
}

export function fetchPipeline() {
  return fetchJson<PipelineData>('/api/pipeline')
}

export function fetchReports() {
  return fetchJson<RunReport[]>('/api/reports')
}

export async function runAgent(payload: {
  agentId: string
  capabilities: string[]
  prompt: string
  model: string
  overrides: RunOverrides
}) {
  const response = await fetch(`${API_BASE}/api/run`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(`Run failed: ${response.status}`)
  }
  return (await response.json()) as RunReport
}
