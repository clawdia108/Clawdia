import { useCallback, useEffect, useMemo, useState, type PropsWithChildren } from 'react'

import type { LogEvent, RunReport } from '../../shared/types'
import {
  AgentContext,
  type AgentContextValue,
  type LogFilter,
  type ThemeMode,
} from './agent-context'

export function AgentProvider({ children }: PropsWithChildren) {
  const [selectedAgentId, setSelectedAgentId] = useState('dealops')
  const [logs, setLogs] = useState<LogEvent[]>([])
  const [reports, setReports] = useState<RunReport[]>([])
  const [theme, setThemeState] = useState<ThemeMode>(() => {
    const saved =
      typeof window !== 'undefined' && typeof window.localStorage?.getItem === 'function'
        ? window.localStorage.getItem('agent-control-studio:theme')
        : null
    return saved === 'dark' ? 'dark' : 'light'
  })
  const [logFilter, setLogFilter] = useState<LogFilter>('all')
  const [autoScroll, setAutoScroll] = useState(true)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    if (typeof window.localStorage?.setItem === 'function') {
      window.localStorage.setItem('agent-control-studio:theme', theme)
    }
  }, [theme])

  const addLog = useCallback((log: LogEvent) => {
    setLogs((current) => [log, ...current].slice(0, 100))
  }, [])

  const clearLogs = useCallback(() => {
    setLogs([])
  }, [])

  const setTheme = useCallback((value: ThemeMode) => {
    setThemeState(value)
  }, [])

  const value = useMemo<AgentContextValue>(
    () => ({
      selectedAgentId,
      setSelectedAgentId,
      logs,
      addLog,
      clearLogs,
      reports,
      setReports,
      theme,
      setTheme,
      logFilter,
      setLogFilter,
      autoScroll,
      setAutoScroll,
    }),
    [
      selectedAgentId,
      logs,
      addLog,
      clearLogs,
      reports,
      theme,
      setTheme,
      logFilter,
      autoScroll,
    ],
  )

  return <AgentContext.Provider value={value}>{children}</AgentContext.Provider>
}
