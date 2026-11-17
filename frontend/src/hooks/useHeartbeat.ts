/** Feature 16 — active work time. Heartbeats are sent only while the user is actually interacting. */
import { useEffect } from 'react'
import { post } from '../api/client'
import { useApp } from '../state/app'
import { isEngaged, onActive } from './activity'

export function useHeartbeat(intervalMs = 30_000) {
  const { project } = useApp()
  useEffect(() => {
    if (!project) return
    const beat = () => { if (isEngaged()) post('/api/time/heartbeat', { project_id: project.id, source: 'app' }).catch(() => {}) }
    beat()
    const id = window.setInterval(beat, intervalMs)
    const off = onActive(beat)
    return () => { window.clearInterval(id); off() }
  }, [project?.id, intervalMs]) // eslint-disable-line react-hooks/exhaustive-deps
}
