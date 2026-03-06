import type { LucideIcon } from 'lucide-react'

interface MetricCardProps {
  label: string
  value: number | string
  icon: LucideIcon
  color: 'violet' | 'blue' | 'emerald' | 'amber' | 'rose' | 'cyan' | 'orange'
  sub?: string
}

const colorMap: Record<string, { icon: string; value: string; glow: string }> = {
  violet: {
    icon: 'text-accent-violet bg-accent-violet/10 border-accent-violet/30',
    value: 'text-accent-violet',
    glow: 'hover:shadow-glow-violet',
  },
  blue: {
    icon: 'text-accent-blue bg-accent-blue/10 border-accent-blue/30',
    value: 'text-accent-blue',
    glow: 'hover:shadow-glow-blue',
  },
  emerald: {
    icon: 'text-accent-emerald bg-accent-emerald/10 border-accent-emerald/30',
    value: 'text-accent-emerald',
    glow: 'hover:shadow-glow-emerald',
  },
  amber: {
    icon: 'text-accent-amber bg-accent-amber/10 border-accent-amber/30',
    value: 'text-accent-amber',
    glow: 'hover:shadow-glow-amber',
  },
  rose: {
    icon: 'text-accent-rose bg-accent-rose/10 border-accent-rose/30',
    value: 'text-accent-rose',
    glow: 'hover:shadow-glow-rose',
  },
  cyan: {
    icon: 'text-accent-cyan bg-accent-cyan/10 border-accent-cyan/30',
    value: 'text-accent-cyan',
    glow: '',
  },
  orange: {
    icon: 'text-accent-orange bg-accent-orange/10 border-accent-orange/30',
    value: 'text-accent-orange',
    glow: '',
  },
}

export default function MetricCard({ label, value, icon: Icon, color, sub }: MetricCardProps) {
  const c = colorMap[color] ?? colorMap.blue
  return (
    <div className={`card p-4 ${c.glow} group transition-all`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="section-label mb-2">{label}</p>
          <p className={`stat-value ${c.value}`}>{value}</p>
          {sub && <p className="text-[11px] text-zinc-500 mt-1 font-medium">{sub}</p>}
        </div>
        <div className={`p-2 rounded-lg border ${c.icon} transition-transform group-hover:scale-105`}>
          <Icon className="w-5 h-5" />
        </div>
      </div>
    </div>
  )
}
