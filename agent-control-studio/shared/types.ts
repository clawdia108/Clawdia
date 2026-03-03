export type LogLevel = 'info' | 'warn' | 'error' | 'success'

export interface AgentSummary {
  id: string
  name: string
  model: string
  defaultModelId?: string
  runtimeAgentId?: string
  runtimeAvailable?: boolean
  status: string
  updated: string
  lane: string
  capabilities: string[]
}

export interface ModelOption {
  id: string
  label: string
  provider: string
  contextWindow: number
  maxTokens: number
  reasoning: boolean
  strengths: string[]
  inputCost: number
  outputCost: number
}

export interface SessionAgentConfig {
  id: string
  name: string
  soulFile: string
  workspacePath: string
  defaultModel: string
  heartbeatModel: string | null
  rateLimitPerMinute: number
  capabilities: string[]
}

export interface SessionConfig {
  routingMode: 'strict_auto' | 'human_override'
  models: {
    autoMode: boolean
    preferredBudgetTier: 'free' | 'economy' | 'standard' | 'premium'
    sandboxDefault: boolean
  }
  agents: Record<string, SessionAgentConfig>
}

export interface FocusBlock {
  id: string
  label: string
  agent: string
  focus: string
}

export interface TodayData {
  title: string
  updatedAt: string
  attention: string[]
  focusBlocks: FocusBlock[]
  tomorrow: string[]
  raw: string
}

export interface IntelData {
  title: string
  updatedAt: string
  highlights: string[]
  actions: string[]
  raw: string
}

export interface PipelineBreakdown {
  pipelineId: number
  pipelineName: string
  count: number
  value: number
}

export interface PipelineAlert {
  id: string
  title: string
  owner: string
  stage: string
  nextStep: string
  priority: 'A' | 'B' | 'C'
}

export interface StageMove {
  id: number
  title: string
  owner: string
  stage: string
  nextActivityDate: string | null
}

export interface PipelineData {
  generatedAt: string
  openDeals: number
  pipelineValue: number
  touchedToday: number
  touchedLast48h: number
  overdueCount: number
  pipelineBreakdown: PipelineBreakdown[]
  alerts: PipelineAlert[]
  stageMoves: StageMove[]
}

export interface RunRequest {
  agentId: string
  capabilities: string[]
  prompt: string
  model: string
  overrides: RunOverrides
}

export interface RunOverrides {
  taskType: string
  temperature: number
  maxTokens: number
  sandbox: boolean
}

export interface RunStats {
  durationMs: number
  emittedLogs: number
}

export interface RouteDecision {
  selectedModel: string
  mode: 'manual' | 'auto'
  reason: string
  matchedRuleId?: string
}

export interface RuntimeExecution {
  requestedAgentId: string
  runtimeAgentId: string
  mode: 'openclaw_local' | 'mock'
  command: string[]
  exitCode: number | null
  actualModel?: string
  sessionId?: string
  provider?: string
}

export interface RunReport {
  id: string
  agentId: string
  agentName: string
  model: string
  route: RouteDecision
  capabilities: string[]
  prompt: string
  overrides: RunOverrides
  status: 'running' | 'completed' | 'failed'
  summary: string
  startedAt: string
  finishedAt: string | null
  filesTouched: string[]
  stats: RunStats
  runtime: RuntimeExecution
  rawResult?: unknown
  error?: string | null
}

export interface LogEvent {
  id: string
  timestamp: string
  level: LogLevel
  actor: string
  message: string
  runId?: string
}
