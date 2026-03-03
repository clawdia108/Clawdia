import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import { AgentProvider } from './context/AgentContext'

const mockFetch = vi.fn()

class MockSocket {
  static instances: MockSocket[] = []

  onmessage: ((event: MessageEvent<string>) => void) | null = null

  onclose: (() => void) | null = null

  constructor() {
    MockSocket.instances.push(this)
  }

  close() {
    this.onclose?.()
  }
}

describe('App', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch)
    vi.stubGlobal('WebSocket', MockSocket as unknown as typeof WebSocket)
    mockFetch.mockImplementation(async (input: string) => {
      if (input.endsWith('/api/agents')) {
        return new Response(
          JSON.stringify([
            {
              id: 'dealops',
              name: 'DealOps',
              model: 'Claude Sonnet 4',
              defaultModelId: 'openai/gpt-5-mini',
              runtimeAgentId: 'pipelinepilot',
              runtimeAvailable: true,
              status: 'publishing hygiene snapshot',
              updated: '13:40',
              lane: 'pipeline hygiene',
              capabilities: ['crm', 'triage'],
            },
          ]),
        )
      }
      if (input.endsWith('/api/files/today')) {
        return new Response(
          JSON.stringify({
            title: 'TODAY',
            updatedAt: '2026-03-03T10:00:00.000Z',
            attention: ['Timebox cron selhal'],
            focusBlocks: [
              {
                id: 'focus-1',
                label: '15:00–15:30',
                agent: 'InboxForge',
                focus: 'Follow-up pack',
              },
            ],
            tomorrow: [],
            raw: 'today',
          }),
        )
      }
      if (input.endsWith('/api/files/intel')) {
        return new Response(
          JSON.stringify({
            title: 'Daily Intel',
            updatedAt: '2026-03-03T10:00:00.000Z',
            highlights: ['Zero-Decay CRM camp'],
            actions: ['Doplnit externi signaly'],
            raw: 'intel',
          }),
        )
      }
      if (input.endsWith('/api/pipeline')) {
        return new Response(
          JSON.stringify({
            generatedAt: '2026-03-03T10:00:00.000Z',
            openDeals: 100,
            pipelineValue: 2168585,
            touchedToday: 0,
            touchedLast48h: 2,
            overdueCount: 12,
            pipelineBreakdown: [],
            alerts: [
              {
                id: '1',
                title: 'Mycroft Mind',
                owner: 'Josef Hofman',
                stage: 'Proposal made',
                nextStep: 'Next activity slipped to 2026-03-06',
                priority: 'A',
              },
            ],
            stageMoves: [],
          }),
        )
      }
      if (input.endsWith('/api/reports')) {
        return new Response(JSON.stringify([]))
      }
      if (input.endsWith('/api/models')) {
        return new Response(
          JSON.stringify([
            {
              id: 'openai/gpt-5-mini',
              label: 'GPT-5-mini',
              provider: 'openai',
              contextWindow: 400000,
              maxTokens: 128000,
              reasoning: true,
              strengths: ['fast_reasoning'],
              inputCost: 0.00025,
              outputCost: 0.002,
            },
          ]),
        )
      }
      if (input.endsWith('/api/session-config')) {
        return new Response(
          JSON.stringify({
            routingMode: 'strict_auto',
            models: {
              autoMode: true,
              preferredBudgetTier: 'economy',
              sandboxDefault: true,
            },
            agents: {
              dealops: {
                id: 'dealops',
                name: 'DealOps',
                soulFile: 'agents/dealops/SOUL.md',
                workspacePath: 'pipedrive/',
                defaultModel: 'openai/gpt-5-mini',
                heartbeatModel: 'openai/gpt-5-nano',
                rateLimitPerMinute: 8,
                capabilities: ['crm', 'triage'],
              },
            },
          }),
        )
      }
      return new Response(JSON.stringify({}))
    })
  })

  it('renders the operator dashboard', async () => {
    const { container } = render(
      <AgentProvider>
        <App />
      </AgentProvider>,
    )

    await screen.findByText('Agent heartbeat')
    await waitFor(() => expect(screen.getByText('Pipeline alerts')).toBeInTheDocument())
    expect(screen.getByText('Run panel')).toBeInTheDocument()
    expect(container).toMatchSnapshot()
  })
})
