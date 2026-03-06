import { CheckCircle2, AlertTriangle, Info, Clock } from 'lucide-react'
import type { ActivityEntry } from '../lib/demo-data'

const typeConfig: Record<string, { icon: typeof Info; color: string }> = {
  success: { icon: CheckCircle2, color: 'text-accent-emerald' },
  info: { icon: Info, color: 'text-accent-blue' },
  warning: { icon: AlertTriangle, color: 'text-accent-amber' },
  pending: { icon: Clock, color: 'text-accent-violet' },
}

export default function ActivityItem({ entry }: { entry: ActivityEntry }) {
  const cfg = typeConfig[entry.type] ?? typeConfig.info
  const Icon = cfg.icon

  return (
    <div className="flex items-start gap-2.5 py-2.5 group hover:bg-zinc-800/30 -mx-3 px-3 transition-colors rounded-lg">
      <div className={`mt-0.5 ${cfg.color}`}>
        <Icon className="w-3.5 h-3.5" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs text-zinc-300 font-medium truncate">
          <span className="text-zinc-100 font-semibold">{entry.agent}</span>
          <span className="text-zinc-600 mx-1.5">·</span>
          <span className={cfg.color}>{entry.action}</span>
        </p>
        <p className="text-[11px] text-zinc-500 truncate mt-0.5">{entry.detail}</p>
      </div>
      <span className="text-[10px] text-zinc-600 font-mono shrink-0 mt-0.5">{entry.time}</span>
    </div>
  )
}
