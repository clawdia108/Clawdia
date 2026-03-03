import type { AgentSummary } from '../../shared/types'
import { SkeletonCard } from './SkeletonCard'

interface AgentListProps {
  agents: AgentSummary[]
  selectedAgentId: string
  onSelect: (agentId: string) => void
  loading: boolean
}

export function AgentList({ agents, selectedAgentId, onSelect, loading }: AgentListProps) {
  return (
    <section className="panel agents">
      <div className="panel-head">
        <h2>Agents</h2>
        <span className="tag">live roster</span>
      </div>
      {loading ? (
        <div className="stack">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : (
        <div className="agent-list">
          {agents.map((agent) => (
            <button
              key={agent.id}
              type="button"
              className={`agent-card ${selectedAgentId === agent.id ? 'selected' : ''}`}
              onClick={() => onSelect(agent.id)}
            >
              <header>
                <div>
                  <p className="eyebrow">{agent.id}</p>
                  <h3>{agent.name}</h3>
                </div>
                <span className="badge">{agent.updated}</span>
              </header>
              <p className="status">{agent.status}</p>
              <p className="meta">Model: {agent.model}</p>
              <p className="meta">Lane: {agent.lane}</p>
              <p className="meta">
                Runtime: {agent.runtimeAgentId ?? 'n/a'} {agent.runtimeAvailable ? 'online' : 'missing'}
              </p>
            </button>
          ))}
        </div>
      )}
    </section>
  )
}
