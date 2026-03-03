import { useMemo, useState } from 'react'

import type { AgentSummary, ModelOption, RunOverrides } from '../../shared/types'

const taskTypeOptions = [
  { value: 'daily_plan', label: 'Daily plan' },
  { value: 'crm_hygiene', label: 'CRM hygiene' },
  { value: 'follow_up', label: 'Follow-up' },
  { value: 'research', label: 'Research' },
  { value: 'review', label: 'Review' },
  { value: 'code_change', label: 'Code change' },
]

interface RunPanelProps {
  agents: AgentSummary[]
  models: ModelOption[]
  selectedAgentId: string
  onAgentChange: (agentId: string) => void
  onRun: (payload: {
    agentId: string
    capabilities: string[]
    prompt: string
    model: string
    overrides: RunOverrides
  }) => Promise<void>
  busy: boolean
  onOpenDrawer: () => void
}

export function RunPanel({
  agents,
  models,
  selectedAgentId,
  onAgentChange,
  onRun,
  busy,
  onOpenDrawer,
}: RunPanelProps) {
  const [prompt, setPrompt] = useState('')
  const [model, setModel] = useState('auto')
  const [temperature, setTemperature] = useState(0.3)
  const [maxTokens, setMaxTokens] = useState(2048)
  const [sandbox, setSandbox] = useState(true)
  const [taskType, setTaskType] = useState('crm_hygiene')

  const agent = useMemo(
    () => agents.find((item) => item.id === selectedAgentId) ?? agents[0],
    [agents, selectedAgentId],
  )
  const [capabilities, setCapabilities] = useState<string[]>(() => agent?.capabilities.slice(0, 2) ?? [])

  const toggleCapability = (capability: string) => {
    setCapabilities((current) =>
      current.includes(capability)
        ? current.filter((item) => item !== capability)
        : [...current, capability],
    )
  }

  const submit = async () => {
    if (!agent || !prompt.trim()) {
      return
    }
    await onRun({
      agentId: agent.id,
      capabilities,
      prompt: prompt.trim(),
      model,
      overrides: {
        taskType,
        temperature,
        maxTokens,
        sandbox,
      },
    })
    setPrompt('')
  }

  return (
    <section className="panel run-panel">
      <div className="panel-head">
        <h2>Run panel</h2>
        <div className="run-panel-head-actions">
          <span className="tag accent">manual trigger</span>
          <button type="button" className="ghost" onClick={onOpenDrawer}>
            Routing drawer
          </button>
        </div>
      </div>
      <label className="field">
        <span>Agent</span>
        <select value={agent?.id ?? ''} onChange={(event) => onAgentChange(event.target.value)}>
          {agents.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Model</span>
        <select value={model} onChange={(event) => setModel(event.target.value)}>
          <option value="auto">Auto route</option>
          {models.map((option) => (
            <option key={option.id} value={option.id}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <div className="field grid-two">
        <label className="field">
          <span>Task type</span>
          <select value={taskType} onChange={(event) => setTaskType(event.target.value)}>
            {taskTypeOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Max tokens</span>
          <input
            type="number"
            min={256}
            step={256}
            value={maxTokens}
            onChange={(event) => setMaxTokens(Number(event.target.value))}
          />
        </label>
      </div>
      <div className="field">
        <span>Capabilities</span>
        <div className="toggle-group">
          {(agent?.capabilities ?? []).map((capability) => (
            <button
              key={capability}
              type="button"
              className={`toggle-pill ${capabilities.includes(capability) ? 'active' : ''}`}
              onClick={() => toggleCapability(capability)}
            >
              {capability}
            </button>
          ))}
        </div>
      </div>
      <label className="field">
        <span>Prompt</span>
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          rows={5}
          placeholder="Tell the selected agent what to do. Keep it crisp; the mock runner will do the rest."
        />
      </label>
      <div className="field grid-two">
        <label className="field">
          <span>Temperature</span>
          <input
            type="number"
            min={0}
            max={1}
            step={0.1}
            value={temperature}
            onChange={(event) => setTemperature(Number(event.target.value))}
          />
        </label>
        <label className="checkbox checkbox-boxed">
          <input
            type="checkbox"
            checked={sandbox}
            onChange={(event) => setSandbox(event.target.checked)}
          />
          sandbox tools only
        </label>
      </div>
      <div className="run-actions">
        <button type="button" className="cta" onClick={() => void submit()} disabled={busy || !agent}>
          {busy ? 'Running…' : 'Run playbook'}
        </button>
        <p className="sub">
          {busy ? 'OpenClaw runtime is streaming logs now.' : 'Cmd+Enter also triggers this form.'}
        </p>
      </div>
      <p className="sub">
        Studio route chooses the requested model, but OpenClaw runtime may still execute with the
        agent&apos;s configured model.
      </p>
    </section>
  )
}
