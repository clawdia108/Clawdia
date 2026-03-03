import express from 'express'
import cors from 'cors'

import type { RunRequest, RunReport, SessionConfig } from '../shared/types'
import { LogHub } from './lib/log-hub'
import { OpenClawRunner } from './lib/openclaw-runner'
import { ReportStore } from './lib/report-store'
import { SessionConfigStore } from './lib/session-config-store'
import {
  buildDefaultSessionConfig,
  getWorkspaceFiles,
  listAgents,
  readModelCatalog,
  readIntelData,
  readPipelineData,
  readTodayData,
  resolveRoute,
  resolveRuntimeAgentId,
} from './lib/workspace-data'

function createRunReport(payload: RunRequest, sessionConfig: SessionConfig): RunReport {
  const agents = listAgents()
  const agent = agents.find((item) => item.id === payload.agentId) ?? agents[0]
  const route = resolveRoute(agent.id, payload.model, payload.overrides, sessionConfig)
  return {
    id: `run-${Date.now()}`,
    agentId: agent.id,
    agentName: agent.name,
    model: route.selectedModel,
    route,
    capabilities: payload.capabilities,
    prompt: payload.prompt,
    overrides: payload.overrides,
    status: 'running',
    summary: 'Run queued. Mock executor is warming up.',
    startedAt: new Date().toISOString(),
    finishedAt: null,
    filesTouched: ['calendar/TODAY.md', 'intel/DAILY-INTEL.md', 'pipedrive/.pipeline_snapshot.json'],
    stats: {
      durationMs: 0,
      emittedLogs: 0,
    },
    runtime: {
      requestedAgentId: agent.id,
      runtimeAgentId: resolveRuntimeAgentId(agent.id),
      mode: 'openclaw_local',
      command: [],
      exitCode: null,
    },
    rawResult: null,
    error: null,
  }
}

export function createApp(logHub: LogHub, reportStore: ReportStore) {
  const app = express()
  const sessionConfigStore = new SessionConfigStore(buildDefaultSessionConfig())
  const runExecutor = new OpenClawRunner(logHub, reportStore)

  app.use(cors())
  app.use(express.json())

  app.get('/api/agents', (_request, response) => {
    response.json(listAgents())
  })

  app.get('/api/files/today', (_request, response) => {
    response.json(readTodayData())
  })

  app.get('/api/files/intel', (_request, response) => {
    response.json(readIntelData())
  })

  app.get('/api/models', (_request, response) => {
    response.json(readModelCatalog())
  })

  app.get('/api/session-config', (_request, response) => {
    response.json(sessionConfigStore.get())
  })

  app.put('/api/session-config', (request, response) => {
    const payload = request.body as SessionConfig
    if (!payload || typeof payload !== 'object' || !payload.agents || !payload.models) {
      response.status(400).json({ error: 'Invalid session config payload' })
      return
    }
    response.json(sessionConfigStore.set(payload))
  })

  app.get('/api/pipeline', (_request, response) => {
    response.json(readPipelineData())
  })

  app.get('/api/reports', (_request, response) => {
    response.json(reportStore.list())
  })

  app.get('/api/reports/latest', (_request, response) => {
    response.json(reportStore.latest())
  })

  app.get('/api/reports/:id', (request, response) => {
    const report = reportStore.get(request.params.id)
    if (!report) {
      response.status(404).json({ error: 'Report not found' })
      return
    }
    response.json(report)
  })

  app.post('/api/run', (request, response) => {
    const payload = request.body as Partial<RunRequest>
    if (
      !payload.agentId ||
      !payload.prompt ||
      !Array.isArray(payload.capabilities) ||
      !payload.overrides
    ) {
      response.status(400).json({ error: 'agentId, capabilities, prompt, and overrides are required' })
      return
    }

    const report = createRunReport({
      agentId: payload.agentId,
      capabilities: payload.capabilities,
      prompt: payload.prompt,
      model: payload.model ?? 'auto',
      overrides: payload.overrides,
    }, sessionConfigStore.get())
    reportStore.add(report)
    logHub.broadcast({
      timestamp: new Date().toISOString(),
      level: 'info',
      actor: 'studio',
      message: `Queued ${report.agentName} run with ${report.model}. ${report.route.reason}`,
      runId: report.id,
    })
    runExecutor.run(report)
    response.status(202).json(report)
  })

  app.get('/api/meta/files', (_request, response) => {
    response.json({ files: getWorkspaceFiles() })
  })

  app.use((error: Error, _request: express.Request, response: express.Response, next: express.NextFunction) => {
    void next
    response.status(500).json({ error: error.message })
  })

  return app
}
