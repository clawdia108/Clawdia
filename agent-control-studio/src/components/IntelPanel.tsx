import type { IntelData, TodayData } from '../../shared/types'
import { SkeletonCard } from './SkeletonCard'

interface IntelPanelProps {
  intel: IntelData | null
  today: TodayData | null
  loading: boolean
}

export function IntelPanel({ intel, today, loading }: IntelPanelProps) {
  return (
    <section className="panel intel">
      <div className="panel-head">
        <h2>Command intel</h2>
        <span className="tag">fallback aware</span>
      </div>
      {loading || !intel ? (
        <div className="stack">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : (
        <>
          <div className="notice-strip">
            {today?.attention[0] ?? 'All calm. No manual fallback banners detected.'}
          </div>
          <div className="bullet-stack">
            {intel.highlights.slice(0, 4).map((item) => (
              <article key={item} className="chip-card">
                {item}
              </article>
            ))}
          </div>
          <div className="actions-list">
            <p className="eyebrow">Next ask for GrowthLab</p>
            {intel.actions.map((item) => (
              <p key={item} className="sub">
                {item}
              </p>
            ))}
          </div>
        </>
      )}
    </section>
  )
}
