import { useCallback, useMemo } from 'react'
import {
  DollarSign,
  TrendingUp,
  Target,
  Activity,
  Flame,
  ThermometerSun,
  Snowflake,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  Users,
  MessageSquare,
  Calendar,
  BarChart3,
} from 'lucide-react'
import { usePolling } from '../hooks/usePolling'
import { api } from '../lib/api'
import MetricCard from '../components/MetricCard'

interface PipelineDeal {
  id: string
  title: string
  value: number
  stage: string
  health_score: number
  lead_score: number
  owner_contact: string
  company: string
  days_in_stage: number
  last_activity: string
  cadence_type: string
  next_touch: string
  velocity_trend: 'up' | 'down' | 'flat'
}

interface RevenueData {
  pipeline_total: number
  weighted_pipeline: number
  monthly_target: number
  monthly_floor: number
  deals_won_mtd: number
  revenue_mtd: number
  avg_deal_size: number
  avg_cycle_days: number
  win_rate: number
  deals_by_stage: Record<string, { count: number; value: number }>
  hot_deals: PipelineDeal[]
  at_risk_deals: PipelineDeal[]
  cadence_stats: {
    active_cadences: number
    touches_today: number
    reply_rate: number
    meetings_booked_mtd: number
  }
  lead_score_distribution: {
    hot: number
    warm: number
    cool: number
    cold: number
  }
}

// Mock data factory — in production this comes from /api/revenue
function getMockRevenue(): RevenueData {
  return {
    pipeline_total: 87500,
    weighted_pipeline: 42300,
    monthly_target: 20000,
    monthly_floor: 13000,
    deals_won_mtd: 3,
    revenue_mtd: 11200,
    avg_deal_size: 4800,
    avg_cycle_days: 23,
    win_rate: 34,
    deals_by_stage: {
      'Lead In': { count: 12, value: 24000 },
      'Qualified': { count: 8, value: 28800 },
      'Proposal': { count: 4, value: 19200 },
      'Negotiation': { count: 2, value: 15500 },
    },
    hot_deals: [
      {
        id: 'd1',
        title: 'TechCorp AI Integration',
        value: 8500,
        stage: 'Negotiation',
        health_score: 82,
        lead_score: 91,
        owner_contact: 'Martin Novak',
        company: 'TechCorp s.r.o.',
        days_in_stage: 4,
        last_activity: '2h ago',
        cadence_type: 'nurture',
        next_touch: 'Tomorrow 10:00',
        velocity_trend: 'up',
      },
      {
        id: 'd2',
        title: 'FinServ Platform Deal',
        value: 12000,
        stage: 'Proposal',
        health_score: 74,
        lead_score: 85,
        owner_contact: 'Jana Kralova',
        company: 'FinServ a.s.',
        days_in_stage: 6,
        last_activity: '1d ago',
        cadence_type: 'nurture',
        next_touch: 'Today 14:00',
        velocity_trend: 'flat',
      },
    ],
    at_risk_deals: [
      {
        id: 'd3',
        title: 'RetailMax Automation',
        value: 7000,
        stage: 'Qualified',
        health_score: 38,
        lead_score: 52,
        owner_contact: 'Petr Svoboda',
        company: 'RetailMax CZ',
        days_in_stage: 18,
        last_activity: '8d ago',
        cadence_type: 'reengagement',
        next_touch: 'Overdue',
        velocity_trend: 'down',
      },
    ],
    cadence_stats: {
      active_cadences: 24,
      touches_today: 8,
      reply_rate: 22,
      meetings_booked_mtd: 6,
    },
    lead_score_distribution: {
      hot: 5,
      warm: 12,
      cool: 18,
      cold: 31,
    },
  }
}

function HealthBadge({ score }: { score: number }) {
  const color =
    score >= 70 ? 'bg-claw-green/15 text-claw-green border-claw-green' :
    score >= 40 ? 'bg-claw-orange/15 text-claw-orange border-claw-orange' :
    'bg-claw-red/15 text-claw-red border-claw-red'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-black border-2 ${color}`}>
      {score}
    </span>
  )
}

function LeadScoreBadge({ score }: { score: number }) {
  const icon =
    score >= 80 ? <Flame className="w-3 h-3" /> :
    score >= 50 ? <ThermometerSun className="w-3 h-3" /> :
    <Snowflake className="w-3 h-3" />
  const color =
    score >= 80 ? 'text-claw-red' :
    score >= 50 ? 'text-claw-orange' :
    'text-claw-blue'
  return (
    <span className={`inline-flex items-center gap-0.5 text-[10px] font-black ${color}`}>
      {icon} {score}
    </span>
  )
}

function VelocityIcon({ trend }: { trend: 'up' | 'down' | 'flat' }) {
  if (trend === 'up') return <ArrowUpRight className="w-3.5 h-3.5 text-claw-green" />
  if (trend === 'down') return <ArrowDownRight className="w-3.5 h-3.5 text-claw-red" />
  return <Minus className="w-3.5 h-3.5 text-warmgray" />
}

function ProgressBar({ current, target, floor }: { current: number; target: number; floor: number }) {
  const pctTarget = Math.min((current / target) * 100, 100)
  const pctFloor = Math.min((floor / target) * 100, 100)
  const color = current >= target ? 'bg-claw-green' : current >= floor ? 'bg-claw-yellow' : 'bg-claw-red'

  return (
    <div className="relative">
      <div className="w-full h-4 bg-sand-200 rounded-lg border-2 border-ink overflow-hidden">
        <div
          className={`h-full ${color} transition-all duration-700 ease-out`}
          style={{ width: `${pctTarget}%` }}
        />
      </div>
      {/* Floor marker */}
      <div
        className="absolute top-0 h-4 border-l-2 border-dashed border-ink/40"
        style={{ left: `${pctFloor}%` }}
      />
      <div className="flex justify-between mt-1">
        <span className="text-[9px] text-warmgray font-bold">€0</span>
        <span className="text-[9px] text-warmgray font-bold" style={{ marginLeft: `${pctFloor - 20}%` }}>
          Floor €{(floor / 1000).toFixed(0)}K
        </span>
        <span className="text-[9px] text-warmgray font-bold">Target €{(target / 1000).toFixed(0)}K</span>
      </div>
    </div>
  )
}

export default function Revenue() {
  // In production: const { data } = usePolling<RevenueData>(useCallback(() => api.getRevenue(), []))
  const data = useMemo(() => getMockRevenue(), [])

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h2 className="text-xl font-black text-ink flex items-center gap-2">
          <DollarSign className="w-5 h-5 text-claw-green" />
          Revenue Machine
        </h2>
        <p className="text-xs text-warmgray font-medium mt-0.5">
          Pipeline health, deal scores, and cadence performance
        </p>
      </div>

      {/* Monthly Progress */}
      <div className="card-naive p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="section-title">Monthly Revenue Progress</h3>
          <span className="text-lg font-black text-ink">
            €{data.revenue_mtd.toLocaleString()}
            <span className="text-warmgray text-sm font-bold"> / €{(data.monthly_target / 1000).toFixed(0)}K</span>
          </span>
        </div>
        <ProgressBar current={data.revenue_mtd} target={data.monthly_target} floor={data.monthly_floor} />
        <div className="flex gap-4 mt-3">
          <span className="text-[11px] text-warmgray font-semibold">
            {data.deals_won_mtd} deals closed · Avg €{data.avg_deal_size.toLocaleString()} · {data.win_rate}% win rate
          </span>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-4 gap-4">
        <MetricCard
          label="Pipeline"
          value={`€${(data.pipeline_total / 1000).toFixed(0)}K`}
          icon={BarChart3}
          color="blue"
          sub={`Weighted: €${(data.weighted_pipeline / 1000).toFixed(0)}K`}
        />
        <MetricCard
          label="Avg Cycle"
          value={`${data.avg_cycle_days}d`}
          icon={Calendar}
          color="yellow"
          sub={`Win rate: ${data.win_rate}%`}
        />
        <MetricCard
          label="Active Cadences"
          value={data.cadence_stats.active_cadences}
          icon={MessageSquare}
          color="purple"
          sub={`${data.cadence_stats.touches_today} touches today`}
        />
        <MetricCard
          label="Meetings MTD"
          value={data.cadence_stats.meetings_booked_mtd}
          icon={Users}
          color="green"
          sub={`${data.cadence_stats.reply_rate}% reply rate`}
        />
      </div>

      {/* Pipeline Funnel */}
      <div className="card-naive p-5">
        <h3 className="section-title mb-3">Pipeline by Stage</h3>
        <div className="space-y-2">
          {Object.entries(data.deals_by_stage).map(([stage, { count, value }]) => {
            const maxValue = Math.max(...Object.values(data.deals_by_stage).map(s => s.value))
            const pct = (value / maxValue) * 100
            return (
              <div key={stage} className="flex items-center gap-3">
                <span className="text-xs font-bold text-ink w-24 shrink-0">{stage}</span>
                <div className="flex-1 h-6 bg-sand-200 rounded-md border-2 border-ink overflow-hidden">
                  <div
                    className="h-full bg-claw-blue/70 transition-all duration-500"
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className="text-xs font-black text-ink w-20 text-right tabular-nums">
                  €{(value / 1000).toFixed(1)}K
                </span>
                <span className="text-[10px] text-warmgray font-bold w-12 text-right">{count} deals</span>
              </div>
            )
          })}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Hot Deals */}
        <div>
          <h3 className="section-title mb-3 flex items-center gap-1.5">
            <Flame className="w-3.5 h-3.5 text-claw-red" />
            Hot Deals
          </h3>
          <div className="space-y-2">
            {data.hot_deals.map(deal => (
              <div key={deal.id} className="card-naive p-3 hover:shadow-naive-yellow transition-shadow">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm font-black text-ink">{deal.title}</p>
                    <p className="text-[11px] text-warmgray font-medium">{deal.company} · {deal.owner_contact}</p>
                  </div>
                  <span className="text-sm font-black text-claw-green">€{deal.value.toLocaleString()}</span>
                </div>
                <div className="flex items-center gap-3 mt-2">
                  <span className="text-[10px] font-bold text-ink bg-sand-200 px-2 py-0.5 rounded border border-ink/10">
                    {deal.stage}
                  </span>
                  <HealthBadge score={deal.health_score} />
                  <LeadScoreBadge score={deal.lead_score} />
                  <VelocityIcon trend={deal.velocity_trend} />
                  <span className="text-[10px] text-warmgray font-medium ml-auto">
                    {deal.days_in_stage}d in stage
                  </span>
                </div>
                <div className="flex items-center justify-between mt-2 pt-2 border-t border-ink/5">
                  <span className="text-[10px] text-warmgray font-medium">
                    Last: {deal.last_activity}
                  </span>
                  <span className="text-[10px] font-bold text-claw-blue">
                    Next: {deal.next_touch}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* At Risk Deals */}
        <div>
          <h3 className="section-title mb-3 flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5 text-claw-orange" />
            At Risk
          </h3>
          <div className="space-y-2">
            {data.at_risk_deals.map(deal => (
              <div key={deal.id} className="card-naive p-3 border-claw-red/30 hover:shadow-naive-red transition-shadow">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm font-black text-ink">{deal.title}</p>
                    <p className="text-[11px] text-warmgray font-medium">{deal.company} · {deal.owner_contact}</p>
                  </div>
                  <span className="text-sm font-black text-claw-orange">€{deal.value.toLocaleString()}</span>
                </div>
                <div className="flex items-center gap-3 mt-2">
                  <span className="text-[10px] font-bold text-ink bg-sand-200 px-2 py-0.5 rounded border border-ink/10">
                    {deal.stage}
                  </span>
                  <HealthBadge score={deal.health_score} />
                  <LeadScoreBadge score={deal.lead_score} />
                  <VelocityIcon trend={deal.velocity_trend} />
                  <span className="text-[10px] text-claw-red font-bold ml-auto">
                    {deal.days_in_stage}d in stage
                  </span>
                </div>
                <div className="flex items-center justify-between mt-2 pt-2 border-t border-ink/5">
                  <span className="text-[10px] text-warmgray font-medium">
                    Last: {deal.last_activity}
                  </span>
                  <span className={`text-[10px] font-bold ${deal.next_touch === 'Overdue' ? 'text-claw-red' : 'text-claw-blue'}`}>
                    {deal.next_touch === 'Overdue' ? '⚠ OVERDUE' : `Next: ${deal.next_touch}`}
                  </span>
                </div>
              </div>
            ))}
          </div>

          {/* Lead Score Distribution */}
          <div className="card-naive p-4 mt-4">
            <h3 className="section-title mb-3">Lead Score Distribution</h3>
            <div className="grid grid-cols-4 gap-2">
              {[
                { label: 'Hot', count: data.lead_score_distribution.hot, icon: Flame, color: 'text-claw-red' },
                { label: 'Warm', count: data.lead_score_distribution.warm, icon: ThermometerSun, color: 'text-claw-orange' },
                { label: 'Cool', count: data.lead_score_distribution.cool, icon: Target, color: 'text-claw-blue' },
                { label: 'Cold', count: data.lead_score_distribution.cold, icon: Snowflake, color: 'text-warmgray' },
              ].map(({ label, count, icon: Icon, color }) => (
                <div key={label} className="text-center">
                  <Icon className={`w-4 h-4 mx-auto ${color}`} />
                  <p className="text-lg font-black text-ink mt-1">{count}</p>
                  <p className="text-[10px] text-warmgray font-bold">{label}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
