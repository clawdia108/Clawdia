import { NavLink } from 'react-router-dom'
import { Crosshair, Users, KanbanSquare, DollarSign, Zap } from 'lucide-react'

const links = [
  { to: '/', icon: Crosshair, label: 'Command Center' },
  { to: '/revenue', icon: DollarSign, label: 'Revenue Machine' },
  { to: '/agents', icon: Users, label: 'The Crew' },
  { to: '/tasks', icon: KanbanSquare, label: 'Ops Board' },
]

export default function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 h-screen w-56 bg-white border-r-3 border-ink flex flex-col z-30">
      <div className="px-5 py-5 flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-claw-yellow border-3 border-ink shadow-naive-sm flex items-center justify-center
          hover:animate-wiggle transition-transform cursor-default">
          <Zap className="w-5 h-5 text-ink fill-ink" />
        </div>
        <div>
          <h1 className="text-sm font-black text-ink tracking-tight">OpenClaw</h1>
          <p className="text-[10px] text-warmgray font-semibold uppercase tracking-widest">live ops</p>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-semibold transition-all duration-150 border-2 ${
                isActive
                  ? 'bg-claw-yellow/15 border-ink text-ink shadow-naive-sm'
                  : 'border-transparent text-warmgray hover:text-ink hover:bg-sand-200/50 hover:border-sand-300'
              }`
            }
          >
            <Icon className="w-4 h-4" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="px-4 py-4 border-t-3 border-ink/10">
        <p className="text-[10px] text-warmgray font-bold uppercase tracking-widest">Clawdia v2 · 7 agents · 21 skills</p>
      </div>
    </aside>
  )
}
