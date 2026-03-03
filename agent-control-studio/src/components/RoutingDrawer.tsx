import { useEffect, useMemo, useState } from 'react'

import type { ModelOption, SessionConfig } from '../../shared/types'

interface RoutingDrawerProps {
  open: boolean
  models: ModelOption[]
  sessionConfig: SessionConfig | null
  onClose: () => void
  onSave: (config: SessionConfig) => Promise<void>
}

export function RoutingDrawer({ open, models, sessionConfig, onClose, onSave }: RoutingDrawerProps) {
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (sessionConfig) {
      setDraft(JSON.stringify(sessionConfig, null, 2))
      setError(null)
    }
  }, [sessionConfig])

  const highlightedModels = useMemo(() => models.slice(0, 6), [models])

  if (!open) {
    return null
  }

  const save = async () => {
    try {
      const parsed = JSON.parse(draft) as SessionConfig
      setError(null)
      setBusy(true)
      await onSave(parsed)
    } catch (saveError) {
      const message = saveError instanceof Error ? saveError.message : 'Invalid JSON payload.'
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="drawer-backdrop" role="presentation" onClick={onClose}>
      <aside
        className="routing-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Routing drawer"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="panel-head">
          <h2>Routing drawer</h2>
          <button type="button" className="ghost" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="drawer-section">
          <p className="eyebrow">Model catalog</p>
          <div className="model-grid">
            {highlightedModels.map((model) => (
              <article key={model.id} className="chip-card">
                <p className="label">{model.label}</p>
                <p className="sub">
                  {model.provider} · {model.reasoning ? 'reasoning' : 'fast path'}
                </p>
                <p className="sub">
                  {model.contextWindow.toLocaleString()} ctx · max {model.maxTokens.toLocaleString()}
                </p>
                <p className="sub">{model.strengths.slice(0, 3).join(', ')}</p>
              </article>
            ))}
          </div>
        </div>

        <div className="drawer-section">
          <p className="eyebrow">Session config</p>
          <p className="sub">
            Session-only overrides for routing defaults, soul paths, workspace paths, and rate limits.
          </p>
          <textarea
            className="json-editor"
            spellCheck={false}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            rows={18}
          />
          {error ? <p className="error-text">{error}</p> : null}
        </div>

        <div className="drawer-actions">
          <button type="button" className="ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="cta" onClick={() => void save()} disabled={busy}>
            {busy ? 'Saving…' : 'Save session config'}
          </button>
        </div>
      </aside>
    </div>
  )
}
