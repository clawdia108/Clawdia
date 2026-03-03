import { useContext } from 'react'

import { AgentContext } from './agent-context'

export function useAgentContext() {
  const context = useContext(AgentContext)
  if (!context) {
    throw new Error('useAgentContext must be used inside AgentProvider')
  }
  return context
}
