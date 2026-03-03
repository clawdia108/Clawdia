import type { TodayData } from '../../shared/types'
import { SkeletonCard } from './SkeletonCard'

interface FocusPanelProps {
  today: TodayData | null
  loading: boolean
}

export function FocusPanel({ today, loading }: FocusPanelProps) {
  return (
    <section className="panel blocks">
      <div className="panel-head">
        <h2>Focus blocks</h2>
        <span className="tag muted">today</span>
      </div>
      {loading || !today ? (
        <div className="stack">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : (
        <ul>
          {today.focusBlocks.map((block) => (
            <li key={block.id}>
              <div>
                <p className="label">{block.label}</p>
                <p className="sub">{block.agent}</p>
              </div>
              <p className="focus">{block.focus}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
