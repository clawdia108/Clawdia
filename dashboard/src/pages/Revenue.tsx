import { deals, pipelineStages, metrics } from '../lib/demo-data'
import { DollarSign, Clock, Heart, ArrowRight } from 'lucide-react'

function healthColor(health: number) {
  if (health >= 80) return { bar: 'bg-emerald-500', text: 'text-emerald-400', badge: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' }
  if (health >= 60) return { bar: 'bg-blue-500', text: 'text-blue-400', badge: 'bg-blue-500/15 text-blue-400 border-blue-500/30' }
  if (health >= 40) return { bar: 'bg-amber-500', text: 'text-amber-400', badge: 'bg-amber-500/15 text-amber-400 border-amber-500/30' }
  return { bar: 'bg-rose-500', text: 'text-rose-400', badge: 'bg-rose-500/15 text-rose-400 border-rose-500/30' }
}

function stageBadgeColor(stage: string) {
  const map: Record<string, string> = {
    'Discovery': 'bg-blue-500/15 text-blue-400 border-blue-500/30',
    'Demo': 'bg-violet-500/15 text-violet-400 border-violet-500/30',
    'Proposal': 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    'Negotiation': 'bg-orange-500/15 text-orange-400 border-orange-500/30',
    'Closed Won': 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  }
  return map[stage] || 'bg-zinc-500/15 text-zinc-400 border-zinc-500/30'
}

const atRiskDeals = [...deals].filter(d => d.health < 60).sort((a, b) => a.health - b.health)
const healthyDeals = [...deals].filter(d => d.health >= 60).sort((a, b) => b.health - a.health)
const sortedDeals = [...atRiskDeals, ...healthyDeals]

const totalPipelineValue = deals.reduce((sum, d) => sum + d.value, 0)
const maxStageValue = Math.max(...pipelineStages.map(s => s.value))

export default function Revenue() {
  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100 tracking-tight">Pipeline</h1>
          <p className="text-sm text-zinc-500 mt-1">
            {deals.length} deals &middot; {atRiskDeals.length} at risk
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="px-5 py-3 rounded-xl border border-zinc-800 bg-zinc-900/80">
            <p className="text-xs text-zinc-500 uppercase tracking-wider mb-0.5">Total Pipeline</p>
            <p className="text-2xl font-bold text-zinc-100 font-mono tabular-nums">
              ${(totalPipelineValue / 1000).toFixed(0)}K
            </p>
          </div>
        </div>
      </div>

      {/* Pipeline Stages Bar */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/80 p-6">
        <h2 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider mb-5">Pipeline Stages</h2>

        {/* Horizontal bar visualization */}
        <div className="flex gap-1 h-10 mb-5 rounded-lg overflow-hidden">
          {pipelineStages.map((stage) => {
            const pct = (stage.value / totalPipelineValue) * 100
            return (
              <div
                key={stage.name}
                className="relative group cursor-default transition-all hover:opacity-90"
                style={{ width: `${pct}%`, backgroundColor: stage.color }}
              >
                <div className="absolute inset-0 flex items-center justify-center">
                  {pct > 12 && (
                    <span className="text-xs font-semibold text-white/90 drop-shadow-sm">
                      {stage.name}
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {/* Stage details */}
        <div className="grid grid-cols-5 gap-3">
          {pipelineStages.map((stage) => (
            <div key={stage.name} className="text-center">
              <div className="w-3 h-3 rounded-full mx-auto mb-2" style={{ backgroundColor: stage.color }} />
              <p className="text-xs font-medium text-zinc-300">{stage.name}</p>
              <p className="text-lg font-bold text-zinc-100 font-mono tabular-nums mt-0.5">
                ${(stage.value / 1000).toFixed(0)}K
              </p>
              <p className="text-xs text-zinc-500">{stage.count} deal{stage.count !== 1 ? 's' : ''}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Deals Grid */}
      <div>
        <h2 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider mb-4">Deals</h2>
        <div className="grid grid-cols-2 xl:grid-cols-3 gap-4">
          {sortedDeals.map((deal) => {
            const hc = healthColor(deal.health)
            return (
              <div
                key={deal.id}
                className="rounded-xl border border-zinc-800 bg-zinc-900/80 p-5 hover:border-zinc-700 transition-all group"
              >
                {/* Top row: Company + Value */}
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3 className="text-base font-semibold text-zinc-100">{deal.company}</h3>
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border mt-1.5 ${stageBadgeColor(deal.stage)}`}>
                      {deal.stage}
                    </span>
                  </div>
                  <p className="text-lg font-bold text-zinc-100 font-mono tabular-nums">
                    ${(deal.value / 1000).toFixed(0)}K
                  </p>
                </div>

                {/* Health Bar */}
                <div className="mb-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-zinc-500">Health</span>
                    <span className={`text-xs font-mono font-semibold ${hc.text}`}>{deal.health}%</span>
                  </div>
                  <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                    <div
                      className={`h-full ${hc.bar} rounded-full transition-all duration-500`}
                      style={{ width: `${deal.health}%` }}
                    />
                  </div>
                </div>

                {/* Next Action */}
                <div className="flex items-start gap-2 mb-3">
                  <ArrowRight className="w-3.5 h-3.5 text-zinc-500 mt-0.5 shrink-0" />
                  <p className="text-xs text-zinc-400">{deal.nextAction}</p>
                </div>

                {/* Footer: Days in stage */}
                <div className="flex items-center justify-between pt-3 border-t border-zinc-800">
                  <div className="flex items-center gap-1.5">
                    <Clock className="w-3 h-3 text-zinc-600" />
                    <span className="text-xs text-zinc-500 font-mono">{deal.daysInStage}d in stage</span>
                  </div>
                  {deal.health < 50 && (
                    <span className="text-xs font-medium text-rose-400">at risk</span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
