import type { RunReport } from '../../shared/types'

interface ReportPanelProps {
  reports: RunReport[]
}

export function ReportPanel({ reports }: ReportPanelProps) {
  const latest = reports[0] ?? null

  return (
    <section className="panel reports">
      <div className="panel-head">
        <h2>Recent runs</h2>
        <span className="tag">{reports.length} tracked</span>
      </div>
      {latest ? (
        <article className="report-highlight">
          <p className="eyebrow">latest</p>
          <h3>{latest.agentName}</h3>
          <p className="status">{latest.summary}</p>
          <p className="meta">
            {latest.model} · {latest.status} · {(latest.stats.durationMs / 1000).toFixed(0)}s
          </p>
        </article>
      ) : (
        <div className="empty-state">No runs yet. The gallery wakes up after the first mock execution.</div>
      )}
      <div className="report-list">
        {reports.slice(0, 4).map((report) => (
          <article key={report.id} className="chip-card">
            <p className="label">{report.agentName}</p>
            <p className="sub">{report.summary}</p>
          </article>
        ))}
      </div>
    </section>
  )
}
