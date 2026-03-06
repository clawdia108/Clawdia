import { agents } from '../lib/demo-data'

const colorMap: Record<string, { border: string; bg: string; dot: string; tag: string }> = {
  violet: {
    border: 'border-violet-500/20',
    bg: 'hover:border-violet-500/40',
    dot: 'bg-violet-500',
    tag: 'bg-violet-500/15 text-violet-400 border-violet-500/25',
  },
  blue: {
    border: 'border-blue-500/20',
    bg: 'hover:border-blue-500/40',
    dot: 'bg-blue-500',
    tag: 'bg-blue-500/15 text-blue-400 border-blue-500/25',
  },
  emerald: {
    border: 'border-emerald-500/20',
    bg: 'hover:border-emerald-500/40',
    dot: 'bg-emerald-500',
    tag: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/25',
  },
  cyan: {
    border: 'border-cyan-500/20',
    bg: 'hover:border-cyan-500/40',
    dot: 'bg-cyan-500',
    tag: 'bg-cyan-500/15 text-cyan-400 border-cyan-500/25',
  },
  amber: {
    border: 'border-amber-500/20',
    bg: 'hover:border-amber-500/40',
    dot: 'bg-amber-500',
    tag: 'bg-amber-500/15 text-amber-400 border-amber-500/25',
  },
  rose: {
    border: 'border-rose-500/20',
    bg: 'hover:border-rose-500/40',
    dot: 'bg-rose-500',
    tag: 'bg-rose-500/15 text-rose-400 border-rose-500/25',
  },
}

const statusConfig: Record<string, { dot: string; label: string }> = {
  active: { dot: 'bg-emerald-500', label: 'Active' },
  idle: { dot: 'bg-zinc-600', label: 'Idle' },
  watching: { dot: 'bg-amber-500', label: 'Watching' },
  sleeping: { dot: 'bg-zinc-700', label: 'Sleeping' },
}

const activeCount = agents.filter(a => a.status === 'active' || a.status === 'watching').length

export default function Agents() {
  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-zinc-100 tracking-tight">Agents</h1>
        <p className="text-sm text-zinc-500 mt-1">
          {activeCount} of {agents.length} active &middot; {agents.reduce((s, a) => s + a.tasksToday, 0)} tasks today
        </p>
      </div>

      {/* Agent Grid */}
      <div className="grid grid-cols-2 xl:grid-cols-3 gap-5">
        {agents.map((agent) => {
          const colors = colorMap[agent.color] || colorMap.violet
          const status = statusConfig[agent.status] || statusConfig.idle

          return (
            <div
              key={agent.id}
              className={`rounded-xl border ${colors.border} bg-zinc-900/80 p-5 transition-all ${colors.bg}`}
            >
              {/* Top: Emoji + Name + Status */}
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">{agent.emoji}</span>
                  <div>
                    <h3 className="text-base font-semibold text-zinc-100">{agent.name}</h3>
                    <p className="text-xs text-zinc-500">{agent.role}</p>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-zinc-800/80 border border-zinc-700/50">
                  <div className={`w-2 h-2 rounded-full ${status.dot} ${agent.status === 'active' ? 'animate-pulse' : ''}`} />
                  <span className="text-xs text-zinc-400">{status.label}</span>
                </div>
              </div>

              {/* Description */}
              <p className="text-sm text-zinc-400 mb-4 leading-relaxed">{agent.description}</p>

              {/* Skills */}
              <div className="flex flex-wrap gap-1.5 mb-4">
                {agent.skills.map((skill) => (
                  <span
                    key={skill}
                    className={`text-xs px-2 py-0.5 rounded-md border ${colors.tag}`}
                  >
                    {skill}
                  </span>
                ))}
              </div>

              {/* Footer */}
              <div className="flex items-center justify-between pt-4 border-t border-zinc-800">
                <div className="flex items-center gap-4">
                  <div>
                    <p className="text-xs text-zinc-600">Tasks</p>
                    <p className="text-sm font-bold text-zinc-200 font-mono">{agent.tasksToday}</p>
                  </div>
                  <div>
                    <p className="text-xs text-zinc-600">Last active</p>
                    <p className="text-sm text-zinc-400 font-mono">{agent.lastActive}</p>
                  </div>
                </div>
              </div>

              {/* Daily Output */}
              <div className="mt-3 px-3 py-2 rounded-lg bg-zinc-800/50 border border-zinc-700/30">
                <p className="text-xs text-zinc-500">
                  <span className="text-zinc-400 font-medium">Today:</span> {agent.dailyOutput}
                </p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
