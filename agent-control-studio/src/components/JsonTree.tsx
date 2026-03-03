interface JsonTreeProps {
  value: unknown
  name?: string
}

function renderPrimitive(value: unknown) {
  if (value === null) {
    return 'null'
  }
  if (typeof value === 'string') {
    return `"${value}"`
  }
  return String(value)
}

export function JsonTree({ value, name = 'root' }: JsonTreeProps) {
  if (value === null || typeof value !== 'object') {
    return (
      <div className="json-leaf">
        <span className="json-key">{name}</span>
        <span className="json-value">{renderPrimitive(value)}</span>
      </div>
    )
  }

  const entries = Array.isArray(value)
    ? value.map((entry, index) => [`[${index}]`, entry] as const)
    : Object.entries(value)

  return (
    <details className="json-node" open>
      <summary>
        <span className="json-key">{name}</span>
        <span className="json-meta">
          {Array.isArray(value) ? `Array(${entries.length})` : `${entries.length} fields`}
        </span>
      </summary>
      <div className="json-children">
        {entries.map(([key, entry]) => (
          <JsonTree key={key} name={key} value={entry} />
        ))}
      </div>
    </details>
  )
}
