import { useEffect, useMemo, useRef } from 'react'

import type { LogEvent } from '../../shared/types'

interface LogStreamProps {
  logs: LogEvent[]
  filter: 'all' | 'info' | 'warn' | 'error' | 'success'
  onFilterChange: (value: 'all' | 'info' | 'warn' | 'error' | 'success') => void
  autoScroll: boolean
  onAutoScrollChange: (value: boolean) => void
  onClear: () => void
}

export function LogStream({
  logs,
  filter,
  onFilterChange,
  autoScroll,
  onAutoScrollChange,
  onClear,
}: LogStreamProps) {
  const feedRef = useRef<HTMLDivElement | null>(null)

  const visibleLogs = useMemo(
    () => (filter === 'all' ? logs : logs.filter((log) => log.level === filter)),
    [filter, logs],
  )

  useEffect(() => {
    if (autoScroll && feedRef.current) {
      feedRef.current.scrollTop = 0
    }
  }, [autoScroll, visibleLogs])

  return (
    <section className="panel log">
      <div className="panel-head">
        <h2>Activity log</h2>
        <span className="tag muted">ws stream</span>
      </div>
      <div className="toolbar">
        <div className="toggle-group">
          {(['all', 'info', 'warn', 'error', 'success'] as const).map((item) => (
            <button
              key={item}
              type="button"
              className={`toggle-pill ${filter === item ? 'active' : ''}`}
              onClick={() => onFilterChange(item)}
            >
              {item}
            </button>
          ))}
        </div>
        <div className="toolbar-actions">
          <label className="checkbox">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(event) => onAutoScrollChange(event.target.checked)}
            />
            stick to fresh logs
          </label>
          <button type="button" className="ghost" onClick={onClear}>
            Clear
          </button>
        </div>
      </div>
      <div ref={feedRef} className="log-feed">
        {visibleLogs.length === 0 ? (
          <div className="empty-state">No logs yet. Trigger a run or wait for a watcher ping.</div>
        ) : (
          visibleLogs.map((item) => (
            <div key={item.id} className={`log-item ${item.level}`}>
              <span className="stamp">{new Date(item.timestamp).toLocaleTimeString('cs-CZ')}</span>
              <div>
                <p className="label">{item.actor}</p>
                <p className="sub">{item.message}</p>
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  )
}
