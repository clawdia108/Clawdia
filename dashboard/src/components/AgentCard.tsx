import type { Agent } from '../lib/demo-data'

const dotColors: Record<string, string> = {
  active: 'bg-accent-emerald',
  idle: 'bg-zinc-500',
  watching: 'bg-accent-amber',
  sleeping: 'bg-zinc-600',
}

const colorAccents: Record<string, { tag: string; border: string }> = {
  violet: { tag: 'border-accent-violet/20 text-accent-violet bg-accent-violet/10', border: 'border-accent-violet/30' },
  blue: { tag: 'border-accent-blue/20 text-accent-blue bg-accent-blue/10', border: 'border-accent-blue/30' },
  emerald: { tag: 'border-accent-emerald/20 text-accent-emerald bg-accent-emerald/10', border: 'border-accent-emerald/30' },
  cyan: { tag: 'border-accent-cyan/20 text-accent-cyan bg-accent-cyan/10', border: 'border-accent-cyan/30' },
  amber: { tag: 'border-accent-amber/20 text-accent-amber bg-accent-amber/10', border: 'border-accent-amber/30' },
  rose: { tag: 'border-accent-rose/20 text-accent-rose bg-accent-rose/10', border: 'border-accent-rose/30' },
}

export default function AgentCard({ agent }: { agent: Agent }) {
  const accent = colorAccents[agent.color] ?? colorAccents.blue
  const isActive = agent.status === 'active'

  return (
    <div className={`card p-4 transition-all ${isActive ? accent.border : ''}`}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <span className="text-xl">{agent.emoji}</span>
          <div>
            <h3 className="text-sm font-semibold text-zinc-100">{agent.name}</h3>
            <p className="text-[11px] text-zinc-500 font-medium">{agent.role}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${dotColors[agent.status] ?? 'bg-zinc-600'} ${isActive ? 'animate-pulse-slow' : ''}`} />
          <span className="text-[11px] text-zinc-500 capitalize">{agent.status}</span>
        </div>
      </div>

      <p className="text-xs text-zinc-400 mb-3 line-clamp-2">{agent.description}</p>

      <div className="flex flex-wrap gap-1 mb-3">
        {agent.skills.slice(0, 4).map(skill => (
          <span key={skill} className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${accent.tag}`}>
            {skill}
          </span>
        ))}
        {agent.skills.length > 4 && (
          <span className="text-[10px] text-zinc-500 font-medium self-center">+{agent.skills.length - 4}</span>
        )}
      </div>

      <div className="flex items-center justify-between text-[11px]">
        <span className="text-zinc-500">{agent.tasksToday} tasks today</span>
        <span className="text-zinc-500 font-mono">{agent.lastActive}</span>
      </div>
    </div>
  )
}
