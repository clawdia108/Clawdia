import { useEffect, useState } from 'react'

import type {
  AgentSummary,
  IntelData,
  ModelOption,
  PipelineData,
  RunOverrides,
  SessionConfig,
  TodayData,
} from '../shared/types'
import { AgentList } from './components/AgentList'
import { FocusPanel } from './components/FocusPanel'
import { IntelPanel } from './components/IntelPanel'
import { LogStream } from './components/LogStream'
import { PipelinePanel } from './components/PipelinePanel'
import { ReportPanel } from './components/ReportPanel'
import { RoutingDrawer } from './components/RoutingDrawer'
import { RunPanel } from './components/RunPanel'
import { ToastStack } from './components/ToastStack'
import { useAgentContext } from './context/useAgentContext'
import { useLogSocket } from './hooks/useLogSocket'
import {
  fetchAgents,
  fetchIntel,
  fetchModels,
  fetchPipeline,
  fetchReports,
  fetchSessionConfig,
  fetchToday,
  runAgent,
  saveSessionConfig,
} from './lib/api'
import './App.css'

interface ToastMessage {
  id: string
  tone: 'info' | 'success' | 'warn' | 'error'
  message: string
}

function App() {
  const {
    selectedAgentId,
    setSelectedAgentId,
    logs,
    clearLogs,
    reports,
    setReports,
    theme,
    setTheme,
    logFilter,
    setLogFilter,
    autoScroll,
    setAutoScroll,
  } = useAgentContext()
  const [agents, setAgents] = useState<AgentSummary[]>([])
  const [today, setToday] = useState<TodayData | null>(null)
  const [intel, setIntel] = useState<IntelData | null>(null)
  const [pipeline, setPipeline] = useState<PipelineData | null>(null)
  const [models, setModels] = useState<ModelOption[]>([])
  const [sessionConfig, setSessionConfig] = useState<SessionConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [runBusy, setRunBusy] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [toasts, setToasts] = useState<ToastMessage[]>([])

  useLogSocket()

  const pushToast = (toast: Omit<ToastMessage, 'id'>) => {
    const nextToast = {
      ...toast,
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    }
    setToasts((current) => [nextToast, ...current].slice(0, 4))
    window.setTimeout(() => {
      setToasts((current) => current.filter((item) => item.id !== nextToast.id))
    }, 3500)
  }

  useEffect(() => {
    const load = async () => {
      const [nextAgents, nextToday, nextIntel, nextPipeline, nextReports, nextModels, nextSessionConfig] = await Promise.all([
        fetchAgents(),
        fetchToday(),
        fetchIntel(),
        fetchPipeline(),
        fetchReports(),
        fetchModels(),
        fetchSessionConfig(),
      ])

      setAgents(nextAgents)
      setToday(nextToday)
      setIntel(nextIntel)
      setPipeline(nextPipeline)
      setReports(nextReports)
      setModels(nextModels)
      setSessionConfig(nextSessionConfig)
      setLoading(false)
    }

    void load()
    const timer = window.setInterval(() => {
      void load()
    }, 30000)

    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
        const button = document.querySelector<HTMLButtonElement>('.run-panel .cta')
        button?.click()
      }
    }

    window.addEventListener('keydown', handleShortcut)

    return () => {
      window.clearInterval(timer)
      window.removeEventListener('keydown', handleShortcut)
    }
  }, [setReports])

  const handleRun = async (payload: {
    agentId: string
    capabilities: string[]
    prompt: string
    model: string
    overrides: RunOverrides
  }) => {
    setRunBusy(true)
    try {
      const report = await runAgent(payload)
      setReports([report, ...reports].slice(0, 10))
      pushToast({
        tone: report.route.mode === 'auto' ? 'success' : 'info',
        message:
          report.route.mode === 'auto'
            ? `${report.agentName}: ${report.route.reason}`
            : `${report.agentName}: manual model override active.`,
      })
    } finally {
      window.setTimeout(() => setRunBusy(false), 1500)
    }
  }

  const handleSessionConfigSave = async (config: SessionConfig) => {
    const saved = await saveSessionConfig(config)
    setSessionConfig(saved)
    setDrawerOpen(false)
    pushToast({
      tone: 'success',
      message: 'Session routing config saved in memory for this studio run.',
    })
  }

  return (
    <div className="app-shell">
      <ToastStack toasts={toasts} />
      <header className="masthead">
        <div>
          <p className="eyebrow">OpenClaw / Control Studio</p>
          <h1>Agent heartbeat</h1>
          <p className="subhead">
            One screen for today&apos;s files, pipeline alerts, live mock logs, and manual agent nudges.
          </p>
        </div>
        <div className="masthead-actions">
          <button
            type="button"
            className="ghost theme-toggle"
            onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
          >
            {theme === 'light' ? 'Dark mode' : 'Light mode'}
          </button>
        </div>
      </header>

      <main className="grid">
        <AgentList
          agents={agents}
          selectedAgentId={selectedAgentId}
          onSelect={setSelectedAgentId}
          loading={loading}
        />
        <PipelinePanel pipeline={pipeline} loading={loading} />
        <RunPanel
          key={selectedAgentId}
          agents={agents}
          models={models}
          selectedAgentId={selectedAgentId}
          onAgentChange={setSelectedAgentId}
          onRun={handleRun}
          busy={runBusy}
          onOpenDrawer={() => setDrawerOpen(true)}
        />
        <LogStream
          logs={logs}
          filter={logFilter}
          onFilterChange={setLogFilter}
          autoScroll={autoScroll}
          onAutoScrollChange={setAutoScroll}
          onClear={clearLogs}
        />
        <FocusPanel today={today} loading={loading} />
        <IntelPanel intel={intel} today={today} loading={loading} />
        <ReportPanel reports={reports} />
      </main>
      <RoutingDrawer
        open={drawerOpen}
        models={models}
        sessionConfig={sessionConfig}
        onClose={() => setDrawerOpen(false)}
        onSave={handleSessionConfigSave}
      />
    </div>
  )
}

export default App
