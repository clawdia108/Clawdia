export default function SystemPulse() {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-zinc-800 bg-zinc-900/50">
      <div className="w-2 h-2 rounded-full bg-accent-emerald animate-pulse-slow" />
      <span className="text-xs font-medium text-accent-emerald">Live</span>
      <span className="text-[11px] text-zinc-500 font-mono">·</span>
      <span className="text-[11px] text-zinc-500 font-mono">4 agents active</span>
    </div>
  )
}
