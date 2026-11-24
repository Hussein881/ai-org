import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import type { OrgEvent } from '@/lib/api'

export type Conn = 'connecting' | 'live' | 'reconnecting'
export type Pulse = { edge: string; until: number }

/** One EventSource for the whole app. Events invalidate the matching queries and feed the ticker. */
export function useLiveEvents() {
  const qc = useQueryClient()
  const [ticker, setTicker] = useState<OrgEvent[]>([])
  const [conn, setConn] = useState<Conn>('connecting')
  const [pulses, setPulses] = useState<Pulse[]>([])
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => {
    const es = new EventSource('/api/stream')
    es.onopen = () => {
      setConn('live')
      void qc.invalidateQueries() // anything may have changed before the stream started or while it was down
    }
    es.onerror = () => setConn('reconnecting') // EventSource retries by itself, sending Last-Event-ID
    es.addEventListener('aiorg', (m) => {
      const e = JSON.parse((m as MessageEvent<string>).data) as OrgEvent
      setTicker((t) => [...t.slice(-29), e])
      if (e.kind === 'role.status') void qc.invalidateQueries({ queryKey: ['roles'] })
      if (e.kind.startsWith('task.') || e.kind.startsWith('run.')) {
        void qc.invalidateQueries({ queryKey: ['tasks'] })
        if (e.task_id) void qc.invalidateQueries({ queryKey: ['task', e.task_id] })
      }
      if (e.kind === 'message') {
        const p = e.payload as { from?: string; to?: string }
        if (p.from && p.to) {
          const pulse = { edge: `${p.from}->${p.to}`, until: Date.now() + 4000 }
          setPulses((x) => [...x.filter((y) => y.until > Date.now()), pulse])
          window.clearTimeout(timer.current)
          timer.current = window.setTimeout(() => setPulses((x) => x.filter((y) => y.until > Date.now())), 4100)
        }
      }
    })
    return () => es.close()
  }, [qc])

  return { ticker, conn, pulses }
}
