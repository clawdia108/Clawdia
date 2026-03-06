import { tasks } from '../lib/demo-data'
import type { TaskItem } from '../lib/demo-data'
import { useState, useMemo } from 'react'

type StatusFilter = 'all' | TaskItem['status']

const filterButtons: { key: StatusFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'running', label: 'Running' },
  { key: 'pending_approval', label: 'Pending' },
  { key: 'queued', label: 'Queued' },
  { key: 'done', label: 'Done' },
]

const priorityConfig: Record<string, { bg: string; text: string }> = {
  critical: { bg: 'bg-rose-500/15', text: 'text-rose-400' },
  high: { bg: 'bg-orange-500/15', text: 'text-orange-400' },
  medium: { bg: 'bg-blue-500/15', text: 'text-blue-400' },
  low: { bg: 'bg-zinc-500/15', text: 'text-zinc-400' },
}

const statusConfig: Record<string, { bg: string; text: string; dot: string }> = {
  running: { bg: 'bg-blue-500/15', text: 'text-blue-400', dot: 'bg-blue-500' },
  pending_approval: { bg: 'bg-amber-500/15', text: 'text-amber-400', dot: 'bg-amber-500' },
  queued: { bg: 'bg-zinc-500/15', text: 'text-zinc-400', dot: 'bg-zinc-500' },
  done: { bg: 'bg-emerald-500/15', text: 'text-emerald-400', dot: 'bg-emerald-500' },
  blocked: { bg: 'bg-rose-500/15', text: 'text-rose-400', dot: 'bg-rose-500' },
}

function statusLabel(s: string) {
  const map: Record<string, string> = {
    running: 'Running',
    pending_approval: 'Pending',
    queued: 'Queued',
    done: 'Done',
    blocked: 'Blocked',
  }
  return map[s] || s
}

// Group tasks by status in a defined order
const statusOrder: TaskItem['status'][] = ['running', 'pending_approval', 'queued', 'done', 'blocked']

export default function Tasks() {
  const [filter, setFilter] = useState<StatusFilter>('all')

  const filtered = useMemo(() => {
    if (filter === 'all') return tasks
    return tasks.filter(t => t.status === filter)
  }, [filter])

  // Group filtered tasks by status
  const grouped = useMemo(() => {
    const groups: Record<string, TaskItem[]> = {}
    for (const s of statusOrder) {
      const items = filtered.filter(t => t.status === s)
      if (items.length > 0) {
        groups[s] = items
      }
    }
    return groups
  }, [filtered])

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100 tracking-tight">Tasks</h1>
          <p className="text-sm text-zinc-500 mt-1">
            {tasks.length} total &middot; {tasks.filter(t => t.status === 'running').length} running &middot; {tasks.filter(t => t.status === 'pending_approval').length} pending approval
          </p>
        </div>
      </div>

      {/* Filter Buttons */}
      <div className="flex items-center gap-2">
        {filterButtons.map((btn) => {
          const isActive = filter === btn.key
          const count = btn.key === 'all' ? tasks.length : tasks.filter(t => t.status === btn.key).length
          return (
            <button
              key={btn.key}
              onClick={() => setFilter(btn.key)}
              className={`px-4 py-2 text-sm font-medium rounded-lg transition-all ${
                isActive
                  ? 'bg-zinc-800 text-zinc-100 border border-zinc-700'
                  : 'text-zinc-500 hover:text-zinc-300 border border-transparent hover:border-zinc-800'
              }`}
            >
              {btn.label}
              <span className={`ml-2 text-xs font-mono ${isActive ? 'text-zinc-400' : 'text-zinc-600'}`}>
                {count}
              </span>
            </button>
          )
        })}
      </div>

      {/* Task Groups */}
      <div className="space-y-8">
        {Object.entries(grouped).map(([status, items]) => {
          const sc = statusConfig[status] || statusConfig.queued
          return (
            <div key={status}>
              {/* Group Header */}
              <div className="flex items-center gap-3 mb-4">
                <div className={`w-2 h-2 rounded-full ${sc.dot}`} />
                <h2 className={`text-sm font-semibold uppercase tracking-wider ${sc.text}`}>
                  {statusLabel(status)}
                </h2>
                <span className="text-xs font-mono text-zinc-600">{items.length}</span>
                <div className="flex-1 h-px bg-zinc-800/80" />
              </div>

              {/* Task Cards */}
              <div className="space-y-3">
                {items.map((task) => {
                  const pc = priorityConfig[task.priority] || priorityConfig.medium
                  const tc = statusConfig[task.status] || statusConfig.queued

                  return (
                    <div
                      key={task.id}
                      className="rounded-xl border border-zinc-800 bg-zinc-900/80 p-4 hover:border-zinc-700 transition-all"
                    >
                      <div className="flex items-start gap-4">
                        {/* Priority Badge */}
                        <span className={`shrink-0 mt-0.5 px-2 py-0.5 rounded-md text-xs font-semibold uppercase ${pc.bg} ${pc.text}`}>
                          {task.priority}
                        </span>

                        {/* Main Content */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-3 mb-1">
                            <h3 className="text-sm font-medium text-zinc-100">{task.title}</h3>
                          </div>
                          <p className="text-xs text-zinc-500 mb-2 truncate">{task.summary}</p>
                          <div className="flex items-center gap-3">
                            <span className="text-xs text-zinc-400 font-medium">{task.agent}</span>
                            <span className="text-zinc-700">&middot;</span>
                            <span className={`inline-flex items-center gap-1 text-xs font-medium ${tc.text}`}>
                              <span className={`w-1.5 h-1.5 rounded-full ${tc.dot}`} />
                              {statusLabel(task.status)}
                            </span>
                          </div>
                        </div>

                        {/* Time */}
                        <span className="text-xs text-zinc-600 font-mono whitespace-nowrap shrink-0">
                          {task.updatedAt}
                        </span>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}

        {Object.keys(grouped).length === 0 && (
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/80 p-12 text-center">
            <p className="text-sm text-zinc-500">No tasks match this filter</p>
          </div>
        )}
      </div>
    </div>
  )
}
