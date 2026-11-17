/** Feature 22 — configurable keyboard shortcuts (defaults avoid browser controls). */
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../state/app'
import { usePanels } from '../state/panels'
import { pauseProps } from '../panels/PausePanel'

const CODE_KEYS: Record<string, string> = { BracketLeft: '[', BracketRight: ']', Slash: '/', Period: '.', Comma: ',', Space: 'Space' }

export function comboFromEvent(e: KeyboardEvent): string {
  const mods = [e.ctrlKey && 'Ctrl', e.metaKey && 'Meta', e.altKey && 'Alt', e.shiftKey && 'Shift'].filter(Boolean) as string[]
  let key = e.code.startsWith('Key') ? e.code.slice(3) : e.code.startsWith('Digit') ? e.code.slice(5) : CODE_KEYS[e.code] ?? e.key
  if (['Control', 'Meta', 'Alt', 'Shift'].includes(e.key)) return ''
  return [...mods, key].join('+')
}

export function emitShortcut(action: string) { window.dispatchEvent(new CustomEvent('refocus:shortcut', { detail: action })) }

export function useShortcuts() {
  const { me, project } = useApp()
  const panels = usePanels()
  const nav = useNavigate()
  useEffect(() => {
    const map = me?.preferences.shortcuts ?? {}
    const byCombo = Object.fromEntries(Object.entries(map).map(([a, c]) => [c, a]))
    const onKey = (e: KeyboardEvent) => {
      const action = byCombo[comboFromEvent(e)]
      if (!action) return
      e.preventDefault()
      const panelType = panels.current?.type
      switch (action) {
        case 'pause_session': if (project) panels.open('pause', pauseProps(project.id)); break
        case 'resume_session': nav('/resume'); break
        case 'save_thought': if (panelType === 'thought') emitShortcut('save_thought'); else if (project) panels.open('thought', { projectId: project.id }); break
        case 'save_checkpoint': if (panelType === 'pause') emitShortcut('save_checkpoint'); else if (project) panels.open('pause', pauseProps(project.id)); break
        case 'panel_back': panels.back(); break
        case 'panel_forward': panels.forward(); break
        case 'older_checkpoint': case 'newer_checkpoint': emitShortcut(action); break
        case 'search': nav('/search'); setTimeout(() => (document.getElementById('smart-search') as HTMLInputElement | null)?.focus(), 50); break
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [me, project, panels, nav])
}

export function useShortcutEvent(action: string, fn: () => void) {
  useEffect(() => {
    const h = (e: Event) => { if ((e as CustomEvent).detail === action) fn() }
    window.addEventListener('refocus:shortcut', h)
    return () => window.removeEventListener('refocus:shortcut', h)
  }, [action, fn])
}
