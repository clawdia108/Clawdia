import { spawn } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import type { LogLevel, RunReport } from '../../shared/types'
import type { LogHub } from './log-hub'
import type { ReportStore } from './report-store'
import { resolveRuntimeAgentId } from './workspace-data'

const workspaceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..')

function inferLevel(line: string): LogLevel {
  const lower = line.toLowerCase()
  if (lower.includes('error') || lower.includes('failed')) {
    return 'error'
  }
  if (lower.includes('warn') || lower.includes('unsupported')) {
    return 'warn'
  }
  if (lower.includes('completed') || lower.includes('ready')) {
    return 'success'
  }
  return 'info'
}

function thinkingForTask(taskType: string) {
  if (taskType === 'code_change' || taskType === 'research') {
    return 'high'
  }
  if (taskType === 'review' || taskType === 'follow_up') {
    return 'medium'
  }
  return 'low'
}

function buildMessage(report: RunReport) {
  return [
    'Agent Control Studio request.',
    `Task type: ${report.overrides.taskType}.`,
    `Requested route model: ${report.route.selectedModel}.`,
    `Sandbox preferred: ${report.overrides.sandbox ? 'yes' : 'no'}.`,
    `Temperature hint: ${report.overrides.temperature}.`,
    `Max tokens hint: ${report.overrides.maxTokens}.`,
    '',
    report.prompt,
  ].join('\n')
}

function extractJsonObject(output: string) {
  const start = output.lastIndexOf('\n{')
  const candidate = start >= 0 ? output.slice(start + 1) : output.trim()
  return candidate.startsWith('{') ? candidate : null
}

interface OpenClawResultPayload {
  payloads?: Array<{
    text?: string
  }>
  meta?: {
    durationMs?: number
    agentMeta?: {
      model?: string
      sessionId?: string
      provider?: string
      usage?: {
        total?: number
      }
    }
  }
}

function buildSummary(report: RunReport, payload: OpenClawResultPayload | null, exitCode: number | null) {
  if (!payload || exitCode !== 0) {
    return `${report.agentName} failed before returning a structured result.`
  }

  const firstText = payload.payloads?.[0]?.text as string | undefined
  const usage = payload.meta?.agentMeta?.usage
  const actualModel = payload.meta?.agentMeta?.model as string | undefined
  const body = firstText?.trim() || 'Run completed without a text payload.'
  const usageSummary =
    usage && typeof usage.total === 'number' ? ` Used ${usage.total.toLocaleString()} tokens.` : ''
  const modelSummary =
    actualModel && actualModel !== report.route.selectedModel
      ? ` Runtime used ${actualModel} instead of requested ${report.route.selectedModel}.`
      : ''

  return `${body}${usageSummary}${modelSummary}`
}

export class OpenClawRunner {
  private readonly logHub: LogHub

  private readonly reportStore: ReportStore

  constructor(logHub: LogHub, reportStore: ReportStore) {
    this.logHub = logHub
    this.reportStore = reportStore
  }

  run(report: RunReport) {
    const runtimeAgentId = resolveRuntimeAgentId(report.agentId)
    const command = [
      'agent',
      '--local',
      '--agent',
      runtimeAgentId,
      '--message',
      buildMessage(report),
      '--thinking',
      thinkingForTask(report.overrides.taskType),
      '--timeout',
      '600',
      '--json',
    ]

    const startedAt = Date.now()
    const runtimeReport: RunReport = {
      ...report,
      runtime: {
        ...report.runtime,
        runtimeAgentId,
        mode: 'openclaw_local',
        command: ['openclaw', ...command],
      },
    }
    this.reportStore.replace(runtimeReport)
    this.logHub.broadcast({
      timestamp: new Date().toISOString(),
      level: 'info',
      actor: 'runner',
      message: `Launching openclaw agent for ${runtimeAgentId}.`,
      runId: report.id,
    })

    const child = spawn('openclaw', command, {
      cwd: workspaceRoot,
      env: process.env,
      stdio: ['ignore', 'pipe', 'pipe'],
    })

    let stdoutBuffer = ''
    let stderrBuffer = ''
    let lineBuffer = ''
    let emittedLogs = 0

    const emitLine = (line: string, actor: string) => {
      const trimmed = line.trim()
      if (!trimmed) {
        return
      }
      if (
        trimmed.startsWith('{') ||
        trimmed.startsWith('}') ||
        trimmed.startsWith('"') ||
        trimmed === '],' ||
        trimmed === '},' ||
        trimmed === ']'
      ) {
        return
      }
      emittedLogs += 1
      this.logHub.broadcast({
        timestamp: new Date().toISOString(),
        level: inferLevel(trimmed),
        actor,
        message: trimmed,
        runId: report.id,
      })
    }

    child.stdout.on('data', (chunk: Buffer) => {
      const text = chunk.toString('utf8')
      stdoutBuffer += text
      lineBuffer += text
      const parts = lineBuffer.split('\n')
      lineBuffer = parts.pop() ?? ''
      for (const part of parts) {
        emitLine(part, runtimeAgentId)
      }
    })

    child.stderr.on('data', (chunk: Buffer) => {
      const text = chunk.toString('utf8')
      stderrBuffer += text
      for (const part of text.split('\n')) {
        emitLine(part, 'openclaw-stderr')
      }
    })

    child.on('error', (error) => {
      const failedReport: RunReport = {
        ...runtimeReport,
        status: 'failed',
        finishedAt: new Date().toISOString(),
        summary: `${report.agentName} failed to launch: ${error.message}`,
        error: error.message,
        stats: {
          durationMs: Date.now() - startedAt,
          emittedLogs,
        },
        runtime: {
          ...runtimeReport.runtime,
          exitCode: -1,
        },
      }
      this.reportStore.replace(failedReport)
      this.logHub.broadcast({
        timestamp: new Date().toISOString(),
        level: 'error',
        actor: 'runner',
        message: failedReport.summary,
        runId: report.id,
      })
    })

    child.on('close', (code) => {
      emitLine(lineBuffer, runtimeAgentId)
      const jsonCandidate = extractJsonObject(stdoutBuffer)
      let parsed: OpenClawResultPayload | null = null
      if (jsonCandidate) {
        try {
          parsed = JSON.parse(jsonCandidate) as OpenClawResultPayload
        } catch {
          parsed = null
        }
      }

      const completed: RunReport = {
        ...runtimeReport,
        status: code === 0 ? 'completed' : 'failed',
        finishedAt: new Date().toISOString(),
        summary: buildSummary(report, parsed, code),
        rawResult: parsed,
        error: code === 0 ? null : stderrBuffer.trim() || 'OpenClaw run failed.',
        stats: {
          durationMs: parsed?.meta?.durationMs ?? Date.now() - startedAt,
          emittedLogs,
        },
        runtime: {
          ...runtimeReport.runtime,
          exitCode: code,
          actualModel: parsed?.meta?.agentMeta?.model,
          sessionId: parsed?.meta?.agentMeta?.sessionId,
          provider: parsed?.meta?.agentMeta?.provider,
        },
      }
      this.reportStore.replace(completed)
      this.logHub.broadcast({
        timestamp: new Date().toISOString(),
        level: code === 0 ? 'success' : 'error',
        actor: 'runner',
        message: `Run ${report.id} ${code === 0 ? 'completed' : 'failed'} and was added to reports.`,
        runId: report.id,
      })
    })
  }
}
