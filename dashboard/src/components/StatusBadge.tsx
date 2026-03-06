const statusStyles: Record<string, string> = {
  running: 'border-accent-blue/30 bg-accent-blue/10 text-accent-blue',
  pending_approval: 'border-accent-amber/30 bg-accent-amber/10 text-accent-amber',
  queued: 'border-zinc-700 bg-zinc-800 text-zinc-400',
  done: 'border-accent-emerald/30 bg-accent-emerald/10 text-accent-emerald',
  blocked: 'border-accent-rose/30 bg-accent-rose/10 text-accent-rose',
}

const statusLabels: Record<string, string> = {
  running: 'running',
  pending_approval: 'pending',
  queued: 'queued',
  done: 'done',
  blocked: 'blocked',
}

const priorityStyles: Record<string, string> = {
  critical: 'border-accent-rose/40 bg-accent-rose/10 text-accent-rose',
  high: 'border-accent-orange/40 bg-accent-orange/10 text-accent-orange',
  medium: 'border-accent-blue/30 bg-accent-blue/10 text-accent-blue',
  low: 'border-zinc-700 bg-zinc-800 text-zinc-400',
}

export function StatusBadge({ status }: { status: string }) {
  const label = statusLabels[status] ?? status.replace(/_/g, ' ')
  return (
    <span className={`badge ${statusStyles[status] ?? 'border-zinc-700 bg-zinc-800 text-zinc-400'}`}>
      {label}
    </span>
  )
}

export function PriorityBadge({ priority }: { priority: string }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wide border ${priorityStyles[priority] ?? 'border-zinc-700 bg-zinc-800 text-zinc-400'}`}>
      {priority}
    </span>
  )
}
