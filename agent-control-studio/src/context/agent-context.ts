import { createContext } from 'react'

import type { LogEvent, LogLevel, RunReport } from '../../shared/types'

export type ThemeMode = 'light' | 'dark'
export type LogFilter = LogLevel | 'all'

export interface AgentContextValue {
  selectedAgentId: string
  setSelectedAgentId: (value: string) => void
  logs: LogEvent[]
  addLog: (log: LogEvent) => void
  clearLogs: () => void
  reports: RunReport[]
  setReports: (reports: RunReport[]) => void
  theme: ThemeMode
  setTheme: (theme: ThemeMode) => void
  logFilter: LogFilter
  setLogFilter: (filter: LogFilter) => void
  autoScroll: boolean
  setAutoScroll: (value: boolean) => void
}

export const AgentContext = createContext<AgentContextValue | null>(null)
