import chokidar from 'chokidar'
import { WebSocketServer, type WebSocket } from 'ws'

import type { LogEvent, RunReport } from '../../shared/types'
import type { ReportStore } from './report-store'

function makeEvent(event: Omit<LogEvent, 'id'>): LogEvent {
  return {
    ...event,
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
  }
}

const ambientMessages = [
  'Lobsters are listening… runtime tail is quiet for now.',
  'Bridge pinged the board. Nothing exploded.',
  'Knowledge sync glanced at the fallback files.',
  'Pipeline heartbeat says the shell is steady.',
]

export class LogHub {
  private readonly wss: WebSocketServer

  private readonly reportStore: ReportStore

  private sockets = new Set<WebSocket>()

  private ambientTimer: NodeJS.Timeout | null = null

  constructor(wss: WebSocketServer, reportStore: ReportStore) {
    this.wss = wss
    this.reportStore = reportStore
  }

  attach() {
    this.wss.on('connection', (socket) => {
      this.sockets.add(socket)
      socket.send(
        JSON.stringify(
          makeEvent({
            timestamp: new Date().toISOString(),
            level: 'info',
            actor: 'studio',
            message: 'Socket online. Lobsters are listening… runtime feed armed.',
          }),
        ),
      )

      socket.on('close', () => {
        this.sockets.delete(socket)
      })
    })
  }

  startAmbientFeed() {
    if (this.ambientTimer) {
      return
    }

    this.ambientTimer = setInterval(() => {
      if (this.sockets.size === 0) {
        return
      }

      const message = ambientMessages[Math.floor(Math.random() * ambientMessages.length)]
      this.broadcast({
        timestamp: new Date().toISOString(),
        level: 'info',
        actor: 'heartbeat',
        message,
      })
    }, 12000)
  }

  watchFiles(filePaths: string[]) {
    const watcher = chokidar.watch(filePaths, { ignoreInitial: true })
    watcher.on('change', (filePath) => {
      this.broadcast({
        timestamp: new Date().toISOString(),
        level: 'warn',
        actor: 'watcher',
        message: `Detected change in ${filePath.split('/').slice(-2).join('/')}`,
      })
    })
  }

  broadcast(event: Omit<LogEvent, 'id'>) {
    const payload = JSON.stringify(makeEvent(event))
    for (const socket of this.sockets) {
      if (socket.readyState === socket.OPEN) {
        socket.send(payload)
      }
    }
  }

  runMockSequence(report: RunReport) {
    const steps = [
      { level: 'info', actor: report.agentName, message: `Loading ${report.capabilities.join(', ') || 'default'} capability stack.` },
      { level: 'info', actor: 'gateway', message: `Prompt staged for ${report.agentName} using ${report.model}.` },
      { level: 'warn', actor: 'watcher', message: 'TODAY.md is in manual fallback, keeping the run in safe mode.' },
      { level: 'info', actor: report.agentName, message: 'Synthesizing pipeline and intel context.' },
      { level: 'success', actor: 'reviewer', message: 'Mock run passed lightweight QA guard.' },
    ] as const

    steps.forEach((step, index) => {
      setTimeout(() => {
        this.broadcast({
          timestamp: new Date().toISOString(),
          level: step.level,
          actor: step.actor,
          message: step.message,
          runId: report.id,
        })
      }, (index + 1) * 1000)
    })

    setTimeout(() => {
      const completed: RunReport = {
        ...report,
        status: 'completed',
        summary: `${report.agentName} mocked a clean pass across workspace files and emitted a concise operator summary.`,
        finishedAt: new Date().toISOString(),
        stats: {
          durationMs: steps.length * 1000,
          emittedLogs: steps.length,
        },
      }
      this.reportStore.replace(completed)
      this.broadcast({
        timestamp: new Date().toISOString(),
        level: 'success',
        actor: 'studio',
        message: `Run ${report.id} completed. Report ready in gallery.`,
        runId: report.id,
      })
    }, (steps.length + 1) * 1000)
  }
}
