import { useEffect, useRef } from 'react'

import type { LogEvent } from '../../shared/types'
import { useAgentContext } from '../context/useAgentContext'

const WS_BASE =
  import.meta.env.VITE_WS_BASE ??
  `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/logs`

export function useLogSocket() {
  const { addLog } = useAgentContext()
  const retryRef = useRef<number | null>(null)

  useEffect(() => {
    let socket: WebSocket | null = null
    let cancelled = false

    const connect = () => {
      socket = new WebSocket(WS_BASE)

      socket.onmessage = (event) => {
        const payload = JSON.parse(event.data) as LogEvent
        addLog(payload)
      }

      socket.onclose = () => {
        if (cancelled) {
          return
        }
        retryRef.current = window.setTimeout(connect, 1500)
      }
    }

    connect()

    return () => {
      cancelled = true
      if (retryRef.current) {
        window.clearTimeout(retryRef.current)
      }
      socket?.close()
    }
  }, [addLog])
}
