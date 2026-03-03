import type { RunReport } from '../../shared/types'
import { JsonTree } from './JsonTree'

interface ReportDrawerProps {
  report: RunReport | null
  open: boolean
  onClose: () => void
}

export function ReportDrawer({ report, open, onClose }: ReportDrawerProps) {
  if (!open || !report) {
    return null
  }

  return (
    <div className="drawer-backdrop" role="presentation" onClick={onClose}>
      <aside
        className="routing-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Report details"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="panel-head">
          <h2>Run report</h2>
          <button type="button" className="ghost" onClick={onClose}>
            Close
          </button>
        </div>

        <article className="report-highlight">
          <p className="eyebrow">{report.agentName}</p>
          <h3>{report.status === 'completed' ? 'Completed run' : 'Run details'}</h3>
          <p className="status">{report.summary}</p>
          <p className="meta">
            Route wanted {report.route.selectedModel} · runtime used {report.runtime.actualModel ?? 'pending'}
          </p>
        </article>

        <div className="drawer-section">
          <p className="eyebrow">Overview</p>
          <div className="model-grid">
            <article className="chip-card">
              <p className="label">Duration</p>
              <p className="sub">{(report.stats.durationMs / 1000).toFixed(1)} s</p>
            </article>
            <article className="chip-card">
              <p className="label">Logs</p>
              <p className="sub">{report.stats.emittedLogs}</p>
            </article>
            <article className="chip-card">
              <p className="label">Runtime agent</p>
              <p className="sub">{report.runtime.runtimeAgentId}</p>
            </article>
            <article className="chip-card">
              <p className="label">Session</p>
              <p className="sub">{report.runtime.sessionId ?? 'n/a'}</p>
            </article>
          </div>
        </div>

        <div className="drawer-section">
          <p className="eyebrow">Prompt</p>
          <pre className="report-pre">{report.prompt}</pre>
        </div>

        <div className="drawer-section">
          <p className="eyebrow">Raw result</p>
          {report.rawResult ? (
            <div className="json-shell">
              <JsonTree value={report.rawResult} />
            </div>
          ) : (
            <div className="empty-state">No structured JSON result was captured for this run.</div>
          )}
        </div>
      </aside>
    </div>
  )
}
