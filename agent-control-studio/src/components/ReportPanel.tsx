import type { RunReport } from '../../shared/types'

interface ReportPanelProps {
  reports: RunReport[]
  onOpen: (report: RunReport) => void
  onExportAll: () => void
}

export function ReportPanel({ reports, onOpen, onExportAll }: ReportPanelProps) {
  const latest = reports[0] ?? null

  return (
    <section className="panel reports">
      <div className="panel-head">
        <h2>Recent runs</h2>
        <div className="run-panel-head-actions">
          <span className="tag">{reports.length} tracked</span>
          <button type="button" className="ghost" onClick={onExportAll}>
            Export all
          </button>
        </div>
      </div>
      {latest ? (
        <button type="button" className="report-highlight report-button" onClick={() => onOpen(latest)}>
          <p className="eyebrow">latest</p>
          <h3>{latest.agentName}</h3>
          <p className="status">{latest.summary}</p>
          <p className="meta">
            {latest.model} · {latest.status} · {(latest.stats.durationMs / 1000).toFixed(0)}s
          </p>
        </button>
      ) : (
        <div className="empty-state">No runs yet. The gallery wakes up after the first mock execution.</div>
      )}
      <div className="report-grid">
        {reports.slice(0, 5).map((report) => (
          <button
            key={report.id}
            type="button"
            className="chip-card report-card-button"
            onClick={() => onOpen(report)}
          >
            <div className="report-card-head">
              <p className="label">{report.agentName}</p>
              <span className={`priority priority-${report.status === 'completed' ? 'b' : 'a'}`}>
                {report.status === 'completed' ? 'OK' : 'RUN'}
              </span>
            </div>
            <p className="sub">{report.model}</p>
            <p className="sub">{report.summary}</p>
          </button>
        ))}
      </div>
    </section>
  )
}
