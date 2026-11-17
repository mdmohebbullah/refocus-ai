/** Feature 23 — cross-device sync: refetch when data changed on another device. */
import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { get } from '../api/client'

export function useSync(intervalMs = 20_000) {
  const qc = useQueryClient()
  const last = useRef<string | null>(null)
  useEffect(() => {
    const check = async () => {
      if (document.visibilityState !== 'visible') return
      try {
        const s = await get<{ version: string }>('/api/sync/status')
        if (last.current && s.version !== last.current) qc.invalidateQueries({ predicate: q => !['pause-draft'].includes(q.queryKey[0] as string) })
        last.current = s.version
      } catch { /* offline: try again later */ }
    }
    check()
    const id = window.setInterval(check, intervalMs)
    window.addEventListener('focus', check)
    return () => { window.clearInterval(id); window.removeEventListener('focus', check) }
  }, [qc, intervalMs])
}
