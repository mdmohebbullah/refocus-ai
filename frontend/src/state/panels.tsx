/**
 * Feature 5A — Panel Back/Forward.
 *
 * A browser-like history of the pop-ups/side panels opened in this session. Each entry keeps
 * its own form state and scroll position, so going Back or Forward restores exactly what the
 * user had typed. Opening a new panel after going back clears the Forward history.
 * Navigation never saves data by itself.
 */
import { createContext, useCallback, useContext, useMemo, useReducer, type ReactNode } from 'react'

export type PanelType =
  | 'pause' | 'thought' | 'resume' | 'why' | 'source' | 'help' | 'review' | 'checkpoint' | 'break' | 'compare'

export interface PanelEntry {
  key: string
  type: PanelType
  props: Record<string, any>
  state: Record<string, any>
  scroll: number
}

export interface PanelStackState { entries: PanelEntry[]; index: number }

type Action =
  | { t: 'open'; type: PanelType; props: Record<string, any> }
  | { t: 'back' } | { t: 'forward' } | { t: 'close' }
  | { t: 'setState'; key: string; field: string; value: any }
  | { t: 'setScroll'; key: string; scroll: number }

let counter = 0

export function panelReducer(s: PanelStackState, a: Action): PanelStackState {
  switch (a.t) {
    case 'open': {
      const entry: PanelEntry = { key: `p${++counter}`, type: a.type, props: a.props, state: {}, scroll: 0 }
      const kept = s.index >= 0 ? s.entries.slice(0, s.index + 1) : []   // drop Forward history
      return { entries: [...kept, entry], index: kept.length }
    }
    case 'back': return s.index > 0 ? { ...s, index: s.index - 1 } : s
    case 'forward': return s.index < s.entries.length - 1 ? { ...s, index: s.index + 1 } : s
    case 'close': return { entries: [], index: -1 }
    case 'setState':
      return { ...s, entries: s.entries.map(e => e.key === a.key ? { ...e, state: { ...e.state, [a.field]: a.value } } : e) }
    case 'setScroll':
      return { ...s, entries: s.entries.map(e => e.key === a.key ? { ...e, scroll: a.scroll } : e) }
  }
}

interface PanelApi {
  current: PanelEntry | null
  canBack: boolean
  canForward: boolean
  position: { index: number; total: number }
  history: PanelEntry[]
  open: (type: PanelType, props?: Record<string, any>) => void
  back: () => void
  forward: () => void
  close: () => void
  setField: (key: string, field: string, value: any) => void
  setScroll: (key: string, scroll: number) => void
}

const Ctx = createContext<PanelApi | null>(null)

export function PanelProvider({ children }: { children: ReactNode }) {
  const [s, dispatch] = useReducer(panelReducer, { entries: [], index: -1 })
  const open = useCallback((type: PanelType, props: Record<string, any> = {}) => dispatch({ t: 'open', type, props }), [])
  const back = useCallback(() => dispatch({ t: 'back' }), [])
  const forward = useCallback(() => dispatch({ t: 'forward' }), [])
  const close = useCallback(() => dispatch({ t: 'close' }), [])
  const setField = useCallback((key: string, field: string, value: any) => dispatch({ t: 'setState', key, field, value }), [])
  const setScroll = useCallback((key: string, scroll: number) => dispatch({ t: 'setScroll', key, scroll }), [])
  const value = useMemo<PanelApi>(() => ({
    current: s.index >= 0 ? s.entries[s.index] : null,
    canBack: s.index > 0,
    canForward: s.index >= 0 && s.index < s.entries.length - 1,
    position: { index: s.index + 1, total: s.entries.length },
    history: s.entries,
    open, back, forward, close, setField, setScroll,
  }), [s, open, back, forward, close, setField, setScroll])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function usePanels(): PanelApi {
  const v = useContext(Ctx)
  if (!v) throw new Error('usePanels outside PanelProvider')
  return v
}

/** Form state that lives in the current panel's history entry (survives Back/Forward). */
export function usePanelState<T>(field: string, initial: T): [T, (v: T) => void] {
  const { current, setField } = usePanels()
  const key = current?.key ?? ''
  const value = current && field in current.state ? (current.state[field] as T) : initial
  const set = useCallback((v: T) => { if (key) setField(key, field, v) }, [key, field, setField])
  return [value, set]
}
