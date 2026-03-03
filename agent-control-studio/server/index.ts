import 'dotenv/config'

import http from 'node:http'
import { WebSocketServer } from 'ws'

import { createApp } from './app'
import { LogHub } from './lib/log-hub'
import { ReportStore } from './lib/report-store'
import { getWorkspaceFiles } from './lib/workspace-data'

const port = Number(process.env.PORT ?? 4310)

const reportStore = new ReportStore()
const wss = new WebSocketServer({ noServer: true })
const logHub = new LogHub(wss, reportStore)

const app = createApp(logHub, reportStore)
const server = http.createServer(app)

server.on('upgrade', (request, socket, head) => {
  if (request.url !== '/ws/logs') {
    socket.destroy()
    return
  }

  wss.handleUpgrade(request, socket, head, (ws) => {
    wss.emit('connection', ws, request)
  })
})

logHub.attach()
logHub.startAmbientFeed()
logHub.watchFiles(getWorkspaceFiles())

server.listen(port, () => {
  console.log(`Agent Control Studio server listening on http://localhost:${port}`)
})
