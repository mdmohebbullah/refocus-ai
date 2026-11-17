/** Feature 17 — suggest saving a checkpoint after a configurable period without input. */
import { useEffect } from 'react'
import { useApp } from '../state/app'
import { usePanels } from '../state/panels'
import { lastInputAt } from './activity'

let snoozedUntil = 0
let promptedFor = 0
export function snoozeBreak(minutes: number) { snoozedUntil = Date.now() + minutes * 60_000; promptedFor = lastInputAt() }

export function useBreakDetection() {
  const { me, project } = useApp()
  const panels = usePanels()
  const threshold = (me?.preferences.break_threshold_minutes ?? 10) * 60_000
  const enabled = !!me?.preferences.break_reminders && !!project
  useEffect(() => {
    if (!enabled) return
    const id = window.setInterval(() => {
      const idle = Date.now() - lastInputAt()
      if (idle < threshold || Date.now() < snoozedUntil || promptedFor === lastInputAt()) return
      if (panels.current && panels.current.type !== 'break') return  // never interrupt an open panel
      promptedFor = lastInputAt()
      panels.open('break', { projectId: project!.id, idleMinutes: Math.round(idle / 60_000) })
    }, 15_000)
    return () => window.clearInterval(id)
  }, [enabled, threshold, project, panels])
}
