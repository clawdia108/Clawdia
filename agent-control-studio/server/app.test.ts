// @vitest-environment node

import request from 'supertest'
import { describe, expect, it } from 'vitest'
import { WebSocketServer } from 'ws'

import { createApp } from './app'
import { LogHub } from './lib/log-hub'
import { ReportStore } from './lib/report-store'

describe('server routes', () => {
  const reportStore = new ReportStore()
  const wss = new WebSocketServer({ noServer: true })
  const logHub = new LogHub(wss, reportStore)
  const app = createApp(logHub, reportStore)

  it('returns today file data', async () => {
    const response = await request(app).get('/api/files/today')

    expect(response.status).toBe(200)
    expect(response.body.focusBlocks.length).toBeGreaterThan(0)
  })

  it('returns pipeline aggregates', async () => {
    const response = await request(app).get('/api/pipeline')

    expect(response.status).toBe(200)
    expect(response.body.openDeals).toBeGreaterThan(0)
  })

  it('returns model catalog and session config', async () => {
    const [modelsResponse, sessionResponse] = await Promise.all([
      request(app).get('/api/models'),
      request(app).get('/api/session-config'),
    ])

    expect(modelsResponse.status).toBe(200)
    expect(modelsResponse.body.length).toBeGreaterThan(0)
    expect(sessionResponse.status).toBe(200)
    expect(sessionResponse.body.agents.dealops.defaultModel).toBeTruthy()
  })
})
