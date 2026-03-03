import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import matter from 'gray-matter'

import type {
  AgentSummary,
  FocusBlock,
  IntelData,
  ModelOption,
  PipelineAlert,
  PipelineBreakdown,
  PipelineData,
  RouteDecision,
  RunOverrides,
  SessionConfig,
  StageMove,
  TodayData,
} from '../../shared/types'

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const workspaceRoot = path.resolve(projectRoot, '..')

const todayPath = path.join(workspaceRoot, 'calendar', 'TODAY.md')
const intelPath = path.join(workspaceRoot, 'intel', 'DAILY-INTEL.md')
const pipelinePath = path.join(workspaceRoot, 'pipedrive', '.pipeline_snapshot.json')
const agentRegistryPath = path.join(workspaceRoot, 'control-plane', 'agent-registry.json')
const modelRouterPath = path.join(workspaceRoot, 'control-plane', 'model-router.json')
const openClawRoutingPath = path.join(workspaceRoot, 'workspace', 'openclaw.model-routing.json')

const knownAgents: Record<string, Omit<AgentSummary, 'updated' | 'status'>> = {
  dealops: {
    id: 'dealops',
    name: 'DealOps',
    model: 'Claude Sonnet 4',
    lane: 'pipeline hygiene',
    capabilities: ['crm', 'triage', 'hygiene'],
  },
  timebox: {
    id: 'timebox',
    name: 'Timebox',
    model: 'Claude Haiku',
    lane: 'calendar control',
    capabilities: ['calendar', 'daily-plan', 'ops'],
  },
  inboxforge: {
    id: 'inboxforge',
    name: 'InboxForge',
    model: 'Claude Sonnet 4',
    lane: 'outbound drafting',
    capabilities: ['copy', 'follow-up', 'email'],
  },
  reviewer: {
    id: 'reviewer',
    name: 'Reviewer',
    model: 'Claude Opus',
    lane: 'quality gate',
    capabilities: ['qa', 'review', 'guardrails'],
  },
  growthlab: {
    id: 'growthlab',
    name: 'GrowthLab',
    model: 'Claude Sonnet 4',
    lane: 'market intel',
    capabilities: ['research', 'signals', 'trendwatch'],
  },
}

function readText(filePath: string) {
  const raw = fs.readFileSync(filePath, 'utf8')
  const parsed = matter(raw)
  return {
    raw: parsed.content.trim(),
    updatedAt: fs.statSync(filePath).mtime.toISOString(),
  }
}

function getSectionLines(raw: string, heading: string) {
  const lines = raw.split('\n')
  const start = lines.findIndex((line) => line.trim() === heading)
  if (start === -1) {
    return []
  }

  const section: string[] = []
  for (let index = start + 1; index < lines.length; index += 1) {
    const line = lines[index]
    if (line.startsWith('## ')) {
      break
    }
    if (line.trim()) {
      section.push(line.trim())
    }
  }

  return section
}

function stripMarkdown(value: string) {
  return value
    .replace(/\*\*/g, '')
    .replace(/`/g, '')
    .replace(/^[-*]\s+/, '')
    .replace(/^\d+\.\s+/, '')
    .trim()
}

function parseFocusBlocks(lines: string[]): FocusBlock[] {
  return lines
    .map((line, index) => {
      const match = line.match(/^\d+\.\s+\*\*(.+?)\*\*\s+[–-]\s+(.+)$/)
      if (!match) {
        return null
      }
      const blockLabel = stripMarkdown(match[1])
      const [time, ...agentParts] = blockLabel.split(' ')
      return {
        id: `focus-${index + 1}`,
        label: time,
        agent: agentParts.join(' ').trim() || 'Unknown',
        focus: stripMarkdown(match[2]),
      }
    })
    .filter((block): block is FocusBlock => block !== null)
}

export function readTodayData(): TodayData {
  const { raw, updatedAt } = readText(todayPath)
  return {
    title: raw.split('\n')[0].replace(/^#\s+/, ''),
    updatedAt,
    attention: getSectionLines(raw, '## Overdue / Attention').map(stripMarkdown),
    focusBlocks: parseFocusBlocks(getSectionLines(raw, '## Dnešní bloky')),
    tomorrow: getSectionLines(raw, '## Top 10 zítřek (4. 3.)').map(stripMarkdown),
    raw,
  }
}

export function readIntelData(): IntelData {
  const { raw, updatedAt } = readText(intelPath)
  return {
    title: raw.split('\n')[0].replace(/^#\s+/, ''),
    updatedAt,
    highlights: [
      ...getSectionLines(raw, '## Zero-Decay CRM camp'),
      ...getSectionLines(raw, '## AI/agentický trh (rychlé poznámky)'),
    ].map(stripMarkdown),
    actions: getSectionLines(raw, '## Akce pro GrowthLab (až doběhne agent)').map(stripMarkdown),
    raw,
  }
}

interface RawPipelineSnapshot {
  generated_at: string
  totals: {
    open_deals: number
    pipeline_value: number
  }
  pipeline_breakdown: Array<{
    pipeline_id: number
    pipeline_name: string
    count: number
    value: number
  }>
  touched_today: number
  touched_last_48h: number
  stage_moves: Array<{
    id: number
    title: string
    owner: string
    stage: string
    next_activity_date: string | null
  }>
  overdue: Array<{
    id: number
    title: string
    owner: string
    stage: string
    next_activity_date: string | null
    value: number
  }>
}

function rankAlert(value: number, index: number): PipelineAlert['priority'] {
  if (index < 2 || value >= 100000) {
    return 'A'
  }
  if (index < 5) {
    return 'B'
  }
  return 'C'
}

export function readPipelineData(): PipelineData {
  const raw = fs.readFileSync(pipelinePath, 'utf8')
  const parsed = JSON.parse(raw) as RawPipelineSnapshot

  const pipelineBreakdown: PipelineBreakdown[] = parsed.pipeline_breakdown.map((item) => ({
    pipelineId: item.pipeline_id,
    pipelineName: item.pipeline_name,
    count: item.count,
    value: item.value,
  }))

  const alerts: PipelineAlert[] = parsed.overdue.slice(0, 6).map((item, index) => ({
    id: String(item.id),
    title: item.title,
    owner: item.owner,
    stage: item.stage,
    nextStep: item.next_activity_date
      ? `Next activity slipped to ${item.next_activity_date}`
      : 'No next activity scheduled',
    priority: rankAlert(item.value, index),
  }))

  const stageMoves: StageMove[] = parsed.stage_moves.slice(0, 5).map((move) => ({
    id: move.id,
    title: move.title,
    owner: move.owner,
    stage: move.stage,
    nextActivityDate: move.next_activity_date,
  }))

  return {
    generatedAt: parsed.generated_at,
    openDeals: parsed.totals.open_deals,
    pipelineValue: parsed.totals.pipeline_value,
    touchedToday: parsed.touched_today,
    touchedLast48h: parsed.touched_last_48h,
    overdueCount: parsed.overdue.length,
    pipelineBreakdown,
    alerts,
    stageMoves,
  }
}

export function listAgents(): AgentSummary[] {
  const sessionConfig = buildDefaultSessionConfig()
  const today = readTodayData()
  const intel = readIntelData()
  const hasTodayFallback = today.attention.some((item) => item.includes('Timebox cron selhal'))
  const hasIntelFallback = intel.title.toLowerCase().includes('fallback')

  return Object.values(knownAgents).map((agent) => {
    let status = `${agent.lane} nominal`

    if (agent.id === 'timebox' && hasTodayFallback) {
      status = 'manual TODAY fallback active'
    }
    if (agent.id === 'growthlab' && hasIntelFallback) {
      status = 'intel fallback waiting for fresh run'
    }
    if (agent.id === 'dealops') {
      status = 'publishing hygiene snapshot'
    }
    if (agent.id === 'inboxforge') {
      status = 'assembling A/B follow-up pack'
    }
    if (agent.id === 'reviewer') {
      status = 'QA queue watching TASK-1003'
    }

    return {
      ...agent,
      defaultModelId: sessionConfig.agents[agent.id]?.defaultModel,
      status,
      updated: new Date().toLocaleTimeString('cs-CZ', {
        hour: '2-digit',
        minute: '2-digit',
      }),
    }
  })
}

export function getWorkspaceFiles() {
  return [todayPath, intelPath, pipelinePath]
}

interface OpenClawProviderModel {
  id: string
  name: string
  reasoning?: boolean
  contextWindow?: number
  maxTokens?: number
  cost?: {
    input?: number
    output?: number
  }
}

interface OpenClawRoutingConfig {
  models?: {
    providers?: Record<
      string,
      {
        models?: OpenClawProviderModel[]
      }
    >
  }
  agents?: {
    entries?: Record<
      string,
      {
        model?: string
        heartbeat?: {
          model?: string
        }
      }
    >
    defaults?: {
      heartbeat?: {
        model?: string
      }
    }
  }
}

interface AgentRegistryFile {
  agents: Record<
    string,
    {
      display_name?: string
      capabilities?: string[]
      writes_to?: string[]
    }
  >
}

interface ModelRouterFile {
  models: Record<
    string,
    {
      provider: string
      context_window: number
      max_output_tokens: number
      cost_per_1k_input_usd: number
      cost_per_1k_output_usd: number
      strengths: string[]
    }
  >
  routing_rules: Array<{
    id: string
    match?: {
      agent?: string[]
      task_type?: string[]
    }
    lead_model?: string
    model?: string
    output_model?: string
  }>
}

function readJson<T>(filePath: string): T {
  return JSON.parse(fs.readFileSync(filePath, 'utf8')) as T
}

export function readModelCatalog(): ModelOption[] {
  const modelRouter = readJson<ModelRouterFile>(modelRouterPath)
  const openClawRouting = readJson<OpenClawRoutingConfig>(openClawRoutingPath)

  const providerNames = new Map<string, OpenClawProviderModel>()
  for (const [provider, providerConfig] of Object.entries(openClawRouting.models?.providers ?? {})) {
    for (const model of providerConfig.models ?? []) {
      providerNames.set(`${provider}/${model.id}`, model)
    }
  }

  return Object.entries(modelRouter.models).map(([id, model]) => {
    const enriched = providerNames.get(id)
    return {
      id,
      label: enriched?.name ?? id,
      provider: model.provider,
      contextWindow: enriched?.contextWindow ?? model.context_window,
      maxTokens: enriched?.maxTokens ?? model.max_output_tokens,
      reasoning: enriched?.reasoning ?? model.strengths.includes('reasoning'),
      strengths: model.strengths,
      inputCost: enriched?.cost?.input ?? model.cost_per_1k_input_usd,
      outputCost: enriched?.cost?.output ?? model.cost_per_1k_output_usd,
    }
  })
}

export function buildDefaultSessionConfig(): SessionConfig {
  const registry = readJson<AgentRegistryFile>(agentRegistryPath)
  const routing = readJson<OpenClawRoutingConfig>(openClawRoutingPath)

  const agents = Object.entries(registry.agents)
    .filter(([agentId]) => ['dealops', 'timebox', 'inboxforge', 'reviewer', 'growthlab', 'knowledgekeeper'].includes(agentId))
    .reduce<SessionConfig['agents']>((accumulator, [agentId, agent]) => {
      const writesTo = agent.writes_to?.[0] ?? 'knowledge/'
      accumulator[agentId] = {
        id: agentId,
        name: agent.display_name ?? agentId,
        soulFile: `agents/${agentId}/SOUL.md`,
        workspacePath: writesTo.replace(/[^/]+$/, ''),
        defaultModel: routing.agents?.entries?.[agentId]?.model ?? 'openai/gpt-5-mini',
        heartbeatModel:
          routing.agents?.entries?.[agentId]?.heartbeat?.model ??
          routing.agents?.defaults?.heartbeat?.model ??
          null,
        rateLimitPerMinute: agentId === 'reviewer' ? 4 : 8,
        capabilities: agent.capabilities ?? [],
      }
      return accumulator
    }, {})

  return {
    routingMode: 'strict_auto',
    models: {
      autoMode: true,
      preferredBudgetTier: 'economy',
      sandboxDefault: true,
    },
    agents,
  }
}

function matchesRule(
  rule: ModelRouterFile['routing_rules'][number],
  agentId: string,
  taskType: string,
) {
  const agentMatch = !rule.match?.agent || rule.match.agent.includes(agentId)
  const taskTypeMatch = !rule.match?.task_type || rule.match.task_type.includes(taskType)
  return agentMatch && taskTypeMatch
}

export function resolveRoute(
  agentId: string,
  requestedModel: string,
  overrides: RunOverrides,
  sessionConfig: SessionConfig,
): RouteDecision {
  if (requestedModel && requestedModel !== 'auto') {
    return {
      selectedModel: requestedModel,
      mode: 'manual',
      reason: 'Manual model override from the run panel.',
    }
  }

  const modelRouter = readJson<ModelRouterFile>(modelRouterPath)
  const matchedRule = modelRouter.routing_rules.find((rule) => matchesRule(rule, agentId, overrides.taskType))
  const ruleModel = matchedRule?.lead_model ?? matchedRule?.model ?? matchedRule?.output_model
  const configModel = sessionConfig.agents[agentId]?.defaultModel ?? 'openai/gpt-5-mini'
  const selectedModel = ruleModel ?? configModel

  return {
    selectedModel,
    mode: 'auto',
    matchedRuleId: matchedRule?.id,
    reason: matchedRule
      ? `Auto-selected via routing rule "${matchedRule.id}" for ${agentId}/${overrides.taskType}.`
      : `Auto-selected from session config default for ${agentId}.`,
  }
}
