import { Clock, User } from 'lucide-react'
import type { TaskItem } from '../lib/demo-data'
import { StatusBadge, PriorityBadge } from './StatusBadge'

export default function TaskRow({ task }: { task: TaskItem }) {
  const isCritical = task.priority === 'critical'
  const isBlocked = task.status === 'blocked'

  return (
    <div
      className={`card p-3 flex items-start gap-3 ${
        isCritical ? 'border-accent-rose/30 shadow-glow-rose' : ''
      } ${isBlocked && !isCritical ? 'border-accent-rose/20' : ''}`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <PriorityBadge priority={task.priority} />
          <h4 className="text-sm text-zinc-100 font-medium truncate">{task.title}</h4>
        </div>

        <p className="text-[11px] text-zinc-500 line-clamp-1 mb-2">{task.summary}</p>

        <div className="flex items-center gap-3 text-[11px]">
          <span className="flex items-center gap-1 text-zinc-400 font-medium">
            <User className="w-3 h-3" />
            {task.agent}
          </span>
          <StatusBadge status={task.status} />
        </div>
      </div>

      <div className="text-right shrink-0">
        <div className="flex items-center gap-1 text-[11px] text-zinc-500 font-mono">
          <Clock className="w-3 h-3" />
          {task.updatedAt}
        </div>
      </div>
    </div>
  )
}
