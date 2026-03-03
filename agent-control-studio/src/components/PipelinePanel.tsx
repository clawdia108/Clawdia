import type { PipelineData } from '../../shared/types'
import { SkeletonCard } from './SkeletonCard'

interface PipelinePanelProps {
  pipeline: PipelineData | null
  loading: boolean
}

export function PipelinePanel({ pipeline, loading }: PipelinePanelProps) {
  return (
    <section className="panel alerts">
      <div className="panel-head">
        <h2>Pipeline alerts</h2>
        <span className="tag warm">
          {pipeline ? `${pipeline.overdueCount} overdue` : 'syncing'}
        </span>
      </div>
      {loading || !pipeline ? (
        <div className="stack">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : (
        <>
          <div className="metric-row">
            <article className="metric-card">
              <span className="eyebrow">open deals</span>
              <strong>{pipeline.openDeals}</strong>
            </article>
            <article className="metric-card">
              <span className="eyebrow">pipeline value</span>
              <strong>{pipeline.pipelineValue.toLocaleString('cs-CZ')} Kč</strong>
            </article>
          </div>
          <ul>
            {pipeline.alerts.map((alert) => (
              <li key={alert.id}>
                <div>
                  <p className="label">{alert.title}</p>
                  <p className="sub">
                    {alert.owner} · {alert.stage}
                  </p>
                  <p className="sub">{alert.nextStep}</p>
                </div>
                <span className={`priority priority-${alert.priority.toLowerCase()}`}>
                  {alert.priority}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
