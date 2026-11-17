import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { get, getToken, patch, post, setToken } from '../api/client'
import type { Me, Project } from '../api/types'

interface Toast { id: number; text: string; tone: 'ok' | 'error' | 'info'; action?: { label: string; run: () => void } }

interface AppApi {
  me: Me | null
  loading: boolean
  signIn: (email: string, password: string) => Promise<void>
  register: (name: string, email: string, password: string) => Promise<void>
  signOut: () => void
  refreshMe: () => Promise<void>
  project: Project | null
  projects: Project[]
  setProjectId: (id: number | null) => void
  toast: (text: string, tone?: Toast['tone'], action?: Toast['action']) => void
  toasts: Toast[]
  dismissToast: (id: number) => void
  theme: 'light' | 'dark'
}

const Ctx = createContext<AppApi | null>(null)

export function AppProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const [hasToken, setHasToken] = useState(!!getToken())
  const meQ = useQuery({ queryKey: ['me'], queryFn: () => get<Me>('/api/me'), enabled: hasToken, retry: false })
  const projQ = useQuery({ queryKey: ['projects'], queryFn: () => get<{ projects: Project[] }>('/api/projects'), enabled: !!meQ.data })
  const [toasts, setToasts] = useState<Toast[]>([])
  const tid = useRef(0)

  useEffect(() => {
    const out = () => { setHasToken(false); qc.clear() }
    window.addEventListener('refocus:signed-out', out)
    return () => window.removeEventListener('refocus:signed-out', out)
  }, [qc])

  const toast = useCallback((text: string, tone: Toast['tone'] = 'ok', action?: Toast['action']) => {
    const id = ++tid.current
    setToasts(t => [...t, { id, text, tone, action }])
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), action ? 9000 : 4500)
  }, [])

  const signIn = async (email: string, password: string) => {
    const r = await post<{ access_token: string }>('/api/auth/login', { email, password })
    setToken(r.access_token); setHasToken(true); await qc.invalidateQueries()
  }
  const register = async (name: string, email: string, password: string) => {
    const r = await post<{ access_token: string }>('/api/auth/register', { name, email, password })
    setToken(r.access_token); setHasToken(true); await qc.invalidateQueries()
  }
  const signOut = () => { setToken(null); setHasToken(false); qc.clear() }

  const projects = projQ.data?.projects ?? []
  const currentId = meQ.data?.preferences.current_project_id ?? null
  const project = projects.find(p => p.id === currentId) ?? projects[0] ?? null
  const setProjectId = useCallback((id: number | null) => {
    patch('/api/me/preferences', { current_project_id: id }).then(() => qc.invalidateQueries({ queryKey: ['me'] }))
  }, [qc])

  // Theme
  const pref = meQ.data?.preferences.theme ?? 'system'
  const [systemDark, setSystemDark] = useState(() => window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false)
  useEffect(() => {
    const m = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (!m) return
    const h = (e: MediaQueryListEvent) => setSystemDark(e.matches)
    m.addEventListener('change', h)
    return () => m.removeEventListener('change', h)
  }, [])
  const theme: 'light' | 'dark' = pref === 'system' ? (systemDark ? 'dark' : 'light') : pref
  useEffect(() => { document.documentElement.classList.toggle('dark', theme === 'dark') }, [theme])

  const value = useMemo<AppApi>(() => ({
    me: meQ.data ?? null, loading: hasToken && meQ.isLoading,
    signIn, register, signOut, refreshMe: async () => { await qc.invalidateQueries({ queryKey: ['me'] }) },
    project, projects, setProjectId, toast, toasts, dismissToast: (id: number) => setToasts(t => t.filter(x => x.id !== id)), theme,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [meQ.data, meQ.isLoading, hasToken, project, projects, toasts, theme])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useApp(): AppApi {
  const v = useContext(Ctx)
  if (!v) throw new Error('useApp outside AppProvider')
  return v
}

/** Lets the Pause button read the live cursor position from the open editor. */
export const editorBridge: { docId: number | null; getPosition: (() => { cursor: number; paragraph_text: string; paragraph_index: number }) | null; flush: (() => Promise<void>) | null } =
  { docId: null, getPosition: null, flush: null }
