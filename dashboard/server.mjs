import { readdir, readFile, stat } from 'fs/promises'
import { join, resolve, dirname } from 'path'
import { fileURLToPath } from 'url'
import { createServer } from 'http'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(__dirname, '..')
const PORT = 3001

async function readJson(path) {
  try {
    const content = await readFile(join(ROOT, path), 'utf-8')
    return JSON.parse(content)
  } catch {
    return null
  }
}

async function readMd(path) {
  try {
    return await readFile(join(ROOT, path), 'utf-8')
  } catch {
    return null
  }
}

async function readTaskFiles() {
  try {
    const dir = join(ROOT, 'tasks/open')
    const files = await readdir(dir)
    const tasks = await Promise.all(
      files
        .filter(f => f.endsWith('.json'))
        .map(async f => {
          const content = await readFile(join(dir, f), 'utf-8')
          return JSON.parse(content)
        })
    )
    return tasks
  } catch {
    return []
  }
}

async function readDoneTaskFiles() {
  try {
    const dir = join(ROOT, 'tasks/done')
    const files = await readdir(dir)
    const tasks = await Promise.all(
      files
        .filter(f => f.endsWith('.json'))
        .map(async f => {
          const content = await readFile(join(dir, f), 'utf-8')
          return JSON.parse(content)
        })
    )
    return tasks
  } catch {
    return []
  }
}

async function getFileAge(path) {
  try {
    const s = await stat(join(ROOT, path))
    const ageMs = Date.now() - s.mtime.getTime()
    return {
      path,
      mtime: s.mtime.toISOString(),
      ageMinutes: Math.round(ageMs / 60000),
    }
  } catch {
    return null
  }
}

async function getSystemHealth() {
  const criticalFiles = [
    'knowledge/EXECUTION_STATE.json',
    'knowledge/AGENT_INSIGHTS.md',
    'knowledge/TODAY_SUMMARY.md',
    'WORKBOARD.md',
  ]
  const ages = await Promise.all(criticalFiles.map(getFileAge))
  const validAges = ages.filter(Boolean)
  const maxAge = Math.max(...validAges.map(a => a.ageMinutes), 0)

  let status = 'healthy'
  if (maxAge > 120) status = 'critical'
  else if (maxAge > 60) status = 'stale'

  return { status, maxAgeMinutes: maxAge, files: validAges, timestamp: new Date().toISOString() }
}

async function getMemoryEntries() {
  try {
    const dir = join(ROOT, 'memory')
    const files = await readdir(dir)
    const entries = await Promise.all(
      files
        .filter(f => f.endsWith('.md'))
        .sort()
        .reverse()
        .slice(0, 7)
        .map(async f => {
          const content = await readFile(join(dir, f), 'utf-8')
          const s = await stat(join(dir, f))
          return { date: f.replace('.md', ''), content, mtime: s.mtime.toISOString() }
        })
    )
    return entries
  } catch {
    return []
  }
}

function json(res, data, statusCode = 200) {
  res.writeHead(statusCode, {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET',
  })
  res.end(JSON.stringify(data))
}

async function getAlerts() {
  const alerts = await readJson('knowledge/ESCALATION_ALERTS.json')
  return alerts || { generated_at: null, total_alerts: 0, critical: 0, warnings: 0, info: 0, alerts: [] }
}

async function getLearnings() {
  const [learnings, errors] = await Promise.all([
    readMd('.learnings/LEARNINGS.md'),
    readMd('.learnings/ERRORS.md'),
  ])
  return { learnings, errors }
}

async function getRouter() {
  return await readJson('control-plane/model-router.json')
}

const routes = {
  '/api/state': async () => await readJson('knowledge/EXECUTION_STATE.json'),
  '/api/agents': async () => await readJson('control-plane/agent-registry.json'),
  '/api/tasks': async () => {
    const [open, done] = await Promise.all([readTaskFiles(), readDoneTaskFiles()])
    return { open, done }
  },
  '/api/workboard': async () => ({ content: await readMd('WORKBOARD.md') }),
  '/api/pipeline': async () => {
    const [status, hygiene] = await Promise.all([
      readMd('pipedrive/PIPELINE_STATUS.md'),
      readMd('pipedrive/HYGIENE_REPORT.md'),
    ])
    return { status, hygiene }
  },
  '/api/memory': async () => ({ entries: await getMemoryEntries() }),
  '/api/health': async () => await getSystemHealth(),
  '/api/insights': async () => ({ content: await readMd('knowledge/AGENT_INSIGHTS.md') }),
  '/api/alerts': async () => await getAlerts(),
  '/api/learnings': async () => await getLearnings(),
  '/api/router': async () => await getRouter(),
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`)
  const handler = routes[url.pathname]
  if (handler) {
    const data = await handler()
    json(res, data)
  } else {
    json(res, { error: 'Not found' }, 404)
  }
})

server.listen(PORT, () => {
  console.log(`OpenClaw API running on http://localhost:${PORT}`)
})
