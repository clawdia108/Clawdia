import { NavLink } from 'react-router-dom'
import { LayoutDashboard, TrendingUp, Users, ListTodo } from 'lucide-react'

const links = [
  { to: '/', icon: LayoutDashboard, label: 'Command Center' },
  { to: '/revenue', icon: TrendingUp, label: 'Pipeline' },
  { to: '/agents', icon: Users, label: 'Agents' },
  { to: '/tasks', icon: ListTodo, label: 'Tasks' },
]

export default function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 h-screen w-60 bg-surface-1 border-r border-zinc-800 flex flex-col z-30">
      <div className="px-5 py-5 flex items-center gap-3">
        <span className="text-2xl">🐾</span>
        <div>
          <h1 className="text-base font-bold text-zinc-100">Clawdia</h1>
          <p className="text-[10px] text-zinc-500 font-medium uppercase tracking-widest">ai control center</p>
        </div>
      </div>
      <nav className="flex-1 px-3 py-4 space-y-1">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink key={to} to={to} end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                isActive
                  ? 'bg-accent-violet/10 text-accent-violet'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'
              }`
            }>
            <Icon className="w-4 h-4" />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="px-5 py-4 border-t border-zinc-800">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-accent-emerald animate-pulse-slow" />
          <p className="text-[11px] text-zinc-500">6 agents · 21 skills</p>
        </div>
      </div>
    </aside>
  )
}
