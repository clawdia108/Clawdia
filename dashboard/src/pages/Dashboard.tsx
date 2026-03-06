import { agents, activity, metrics } from '../lib/demo-data'
import { Activity, Users, Clock, Lightbulb, TrendingUp, AlertTriangle, Mail, BookOpen } from 'lucide-react'

const typeColors: Record<string, string> = {
  success: 'bg-emerald-500',
  info: 'bg-blue-500',
  warning: 'bg-amber-500',
  pending: 'bg-violet-500',
}

export default function Dashboard() {
  const activeCount = agents.filter(a => a.status === 'active' || a.status === 'watching').length

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100 tracking-tight">Command Center</h1>
          <p className="text-sm text-zinc-500 mt-1 font-mono">
            {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}
          </p>
        </div>
        <div className="flex items-center gap-2.5 px-4 py-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10">
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs font-semibold text-emerald-400">All systems nominal</span>
        </div>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-4 gap-4">
        {[
          {
            icon: Users,
            label: 'Active Agents',
            value: `${metrics.activeAgents}/${metrics.totalAgents}`,
            color: 'violet',
            bg: 'bg-violet-500/10',
            border: 'border-violet-500/20',
            iconColor: 'text-violet-400',
          },
          {
            icon: Activity,
            label: 'Tasks Today',
            value: `${metrics.tasksCompleted}/${metrics.tasksToday}`,
            color: 'blue',
            bg: 'bg-blue-500/10',
            border: 'border-blue-500/20',
            iconColor: 'text-blue-400',
            sub: `${Math.round((metrics.tasksCompleted / metrics.tasksToday) * 100)}% done`,
          },
          {
            icon: Clock,
            label: 'Pending Approvals',
            value: metrics.pendingApprovals,
            color: 'amber',
            bg: 'bg-amber-500/10',
            border: 'border-amber-500/20',
            iconColor: 'text-amber-400',
          },
          {
            icon: Lightbulb,
            label: 'Insights Found',
            value: metrics.insightsToday,
            color: 'emerald',
            bg: 'bg-emerald-500/10',
            border: 'border-emerald-500/20',
            iconColor: 'text-emerald-400',
          },
        ].map((m) => (
          <div
            key={m.label}
            className={`rounded-xl border ${m.border} ${m.bg} p-5`}
          >
            <div className="flex items-center gap-3 mb-3">
              <div className={`p-2 rounded-lg bg-zinc-900/60 ${m.iconColor}`}>
                <m.icon className="w-4 h-4" />
              </div>
              <span className="text-xs font-medium text-zinc-400 uppercase tracking-wider">{m.label}</span>
            </div>
            <p className="text-2xl font-bold text-zinc-100 font-mono tabular-nums">{m.value}</p>
            {m.sub && <p className="text-xs text-zinc-500 mt-1">{m.sub}</p>}
          </div>
        ))}
      </div>

      {/* Two Column Section */}
      <div className="grid grid-cols-5 gap-6">
        {/* Activity Feed — wider */}
        <div className="col-span-3">
          <h2 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider mb-4">Activity Feed</h2>
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/80 divide-y divide-zinc-800/80">
            {activity.map((item) => (
              <div key={item.id} className="flex items-start gap-3 px-5 py-4 hover:bg-zinc-800/30 transition-colors">
                <div className="mt-1.5">
                  <div className={`w-2 h-2 rounded-full ${typeColors[item.type] || 'bg-zinc-500'}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-zinc-200">
                    <span className="font-semibold text-zinc-100">{item.agent}</span>
                    <span className="text-zinc-500 mx-1.5">·</span>
                    <span className="text-zinc-400">{item.action}</span>
                  </p>
                  <p className="text-xs text-zinc-500 mt-0.5 truncate">{item.detail}</p>
                </div>
                <span className="text-xs text-zinc-600 font-mono whitespace-nowrap shrink-0">{item.time}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Quick Stats */}
        <div className="col-span-2">
          <h2 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider mb-4">Quick Stats</h2>
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/80 p-5 space-y-5">
            {[
              {
                icon: TrendingUp,
                label: 'Pipeline Value',
                value: `$${(metrics.pipelineValue / 1000).toFixed(0)}K`,
                color: 'text-emerald-400',
              },
              {
                icon: AlertTriangle,
                label: 'Deals at Risk',
                value: metrics.dealsAtRisk,
                color: 'text-rose-400',
              },
              {
                icon: Mail,
                label: 'Emails Drafted',
                value: metrics.emailsDrafted,
                color: 'text-blue-400',
              },
              {
                icon: BookOpen,
                label: 'Books Processed',
                value: metrics.booksProcessed,
                color: 'text-amber-400',
              },
            ].map((stat) => (
              <div key={stat.label} className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <stat.icon className={`w-4 h-4 ${stat.color}`} />
                  <span className="text-sm text-zinc-400">{stat.label}</span>
                </div>
                <span className="text-lg font-bold text-zinc-100 font-mono tabular-nums">{stat.value}</span>
              </div>
            ))}

            <div className="border-t border-zinc-800 pt-4 mt-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-zinc-500">Task Completion</span>
                <span className="text-xs font-mono text-zinc-400">{Math.round((metrics.tasksCompleted / metrics.tasksToday) * 100)}%</span>
              </div>
              <div className="w-full h-2 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-violet-500 to-blue-500 rounded-full transition-all duration-700"
                  style={{ width: `${(metrics.tasksCompleted / metrics.tasksToday) * 100}%` }}
                />
              </div>
            </div>

            <div className="border-t border-zinc-800 pt-4">
              <p className="text-xs text-zinc-500 mb-3">Agent Status</p>
              <div className="flex flex-wrap gap-2">
                {agents.map((agent) => (
                  <div
                    key={agent.id}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-zinc-800/60 border border-zinc-700/50"
                  >
                    <div className={`w-1.5 h-1.5 rounded-full ${
                      agent.status === 'active' ? 'bg-emerald-500' :
                      agent.status === 'watching' ? 'bg-amber-500' :
                      'bg-zinc-600'
                    }`} />
                    <span className="text-xs text-zinc-400">{agent.emoji} {agent.name}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
