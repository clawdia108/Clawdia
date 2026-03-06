import { readdir, readFile, stat } from 'fs/promises'
import { join, resolve } from 'path'

const ROOT = resolve(import.meta.dir, '..')
const PORT = 3001

async function readJson(path: string) {
  try {
    const content = await readFile(join(ROOT, path), 'utf-8')
    return JSON.parse(content)
  } catch {
    return null
  }
}

async function readMd(path: string) {
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

async function getFileAge(path: string): Promise<{ path: string; mtime: string; ageMinutes: number } | null> {
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
  const validAges = ages.filter(Boolean) as { path: string; mtime: string; ageMinutes: number }[]
  const maxAge = Math.max(...validAges.map(a => a.ageMinutes), 0)

  let status: 'healthy' | 'stale' | 'critical' = 'healthy'
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

Bun.serve({
  port: PORT,
  fetch: async (req) => {
    const url = new URL(req.url)
    const headers = {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET',
    }

    if (url.pathname === '/api/state') {
      const data = await readJson('knowledge/EXECUTION_STATE.json')
      return new Response(JSON.stringify(data), { headers })
    }

    if (url.pathname === '/api/agents') {
      const data = await readJson('control-plane/agent-registry.json')
      return new Response(JSON.stringify(data), { headers })
    }

    if (url.pathname === '/api/tasks') {
      const [open, done] = await Promise.all([readTaskFiles(), readDoneTaskFiles()])
      return new Response(JSON.stringify({ open, done }), { headers })
    }

    if (url.pathname === '/api/workboard') {
      const content = await readMd('WORKBOARD.md')
      return new Response(JSON.stringify({ content }), { headers })
    }

    if (url.pathname === '/api/pipeline') {
      const [status, hygiene] = await Promise.all([
        readMd('pipedrive/PIPELINE_STATUS.md'),
        readMd('pipedrive/HYGIENE_REPORT.md'),
      ])
      return new Response(JSON.stringify({ status, hygiene }), { headers })
    }

    if (url.pathname === '/api/memory') {
      const entries = await getMemoryEntries()
      return new Response(JSON.stringify({ entries }), { headers })
    }

    if (url.pathname === '/api/health') {
      const health = await getSystemHealth()
      return new Response(JSON.stringify(health), { headers })
    }

    if (url.pathname === '/api/insights') {
      const content = await readMd('knowledge/AGENT_INSIGHTS.md')
      return new Response(JSON.stringify({ content }), { headers })
    }

    return new Response(JSON.stringify({ error: 'Not found' }), { status: 404, headers })
  },
})

console.log(`OpenClaw API running on http://localhost:${PORT}`)
