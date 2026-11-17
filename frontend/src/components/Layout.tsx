import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import {
  Bot, BookOpen, Clock3, FolderKanban, History, LayoutDashboard, Lightbulb, LogOut, Moon, PanelLeftClose, PanelLeftOpen,
  Pause, PlayCircle, Search, Settings, Sun, AppWindow, X,
} from 'lucide-react'
import { useApp } from '../state/app'
import { usePanels } from '../state/panels'
import { patch } from '../api/client'
import { Button, cx } from './ui'
import { PanelHost } from './PanelHost'
import { useShortcuts } from '../hooks/useShortcuts'
import { useHeartbeat } from '../hooks/useHeartbeat'
import { useBreakDetection } from '../hooks/useBreakDetection'
import { useSync } from '../hooks/useSync'
import { pauseProps } from '../panels/PausePanel'

export const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/projects', label: 'My Projects', icon: FolderKanban },
  { to: '/tabs', label: 'Browser Tabs', icon: AppWindow },
  { to: '/activity', label: 'Recent Activity', icon: Clock3 },
  { to: '/history', label: 'History & Timeline', icon: History },
  { to: '/checkpoints', label: 'Pause & Checkpoints', icon: Pause },
  { to: '/thoughts', label: 'Unfinished Thoughts', icon: Lightbulb },
  { to: '/resume', label: 'Resume Workspace', icon: PlayCircle },
  { to: '/notes', label: 'Notes & References', icon: BookOpen },
  { to: '/assistant', label: 'AI Assistant', icon: Bot },
  { to: '/search', label: 'Smart Search', icon: Search },
  { to: '/settings', label: 'Settings & Privacy', icon: Settings },
]

export function Layout({ children }: { children: ReactNode }) {
  const { me, project, projects, setProjectId, signOut, theme, toasts, dismissToast, refreshMe } = useApp()
  const panels = usePanels()
  const nav = useNavigate()
  const [collapsed, setCollapsed] = useState(() => { try { return localStorage.getItem('refocus.sidebar') === '1' } catch { return false } })
  const [mobileOpen, setMobileOpen] = useState(false)
  useShortcuts()
  useHeartbeat()
  useBreakDetection()
  useSync()

  // The extension's “Pause session” button and break notification open /?pause=1.
  const loc = useLocation()
  useEffect(() => {
    if (project && new URLSearchParams(loc.search).get('pause') === '1') {
      panels.open('pause', pauseProps(project.id))
      nav(loc.pathname, { replace: true })
    }
  }, [loc.search, project?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = () => { const v = !collapsed; setCollapsed(v); try { localStorage.setItem('refocus.sidebar', v ? '1' : '0') } catch { /* ignore */ } }
  const toggleTheme = async () => { await patch('/api/me/preferences', { theme: theme === 'dark' ? 'light' : 'dark' }); refreshMe() }

  const sidebar = (
    <nav aria-label="Main" className="flex h-full flex-col gap-0.5 p-2">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink key={to} to={to} end={end} onClick={() => setMobileOpen(false)} title={collapsed ? label : undefined}
          className={({ isActive }) => cx('flex h-10 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors',
            isActive ? 'bg-fact-bg text-fact' : 'text-muted hover:bg-canvas hover:text-ink')}>
          <Icon className="h-[18px] w-[18px] shrink-0" aria-hidden />
          <span className={cx(collapsed && 'lg:sr-only')}>{label}</span>
        </NavLink>
      ))}
      <div className="mt-auto border-t border-line pt-2">
        <button onClick={toggle} className="hidden h-10 w-full items-center gap-3 rounded-md px-3 text-sm text-muted hover:bg-canvas lg:flex"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
          {collapsed ? <PanelLeftOpen className="h-[18px] w-[18px]" /> : <PanelLeftClose className="h-[18px] w-[18px]" />}
          {!collapsed && 'Collapse'}
        </button>
      </div>
    </nav>
  )

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-16 shrink-0 items-center gap-2 border-b-2 border-ink/70 bg-surface px-2 sm:gap-3 sm:px-4">
        <button className="shrink-0 rounded-md p-2 lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open menu"><PanelLeftOpen className="h-5 w-5" /></button>
        <button onClick={() => nav('/')} className="hidden shrink-0 items-center gap-2 pr-2 sm:flex" aria-label="Re-Focus AI home">
          <img src="/favicon.svg" alt="" className="h-7 w-7" />
          <span className="hidden font-hand text-[28px] font-bold leading-none text-navy sm:inline">Re-Focus AI</span>
        </button>
        <label className="sr-only" htmlFor="project-select">Current project</label>
        <select id="project-select" value={project?.id ?? ''} onChange={e => setProjectId(Number(e.target.value) || null)}
          className="h-9 min-w-0 flex-1 truncate rounded-md border border-line bg-surface px-2 text-sm sm:max-w-[220px] sm:flex-none">
          {projects.length === 0 && <option value="">No projects yet</option>}
          {projects.map(p => <option key={p.id} value={p.id}>{p.pinned ? '★ ' : ''}{p.name}</option>)}
        </select>
        <div className="ml-auto flex shrink-0 items-center gap-1 sm:gap-2">
          {me?.privacy.private_mode && <span className="hidden rounded-full border border-line px-2 py-0.5 text-xs text-muted md:inline">Private mode</span>}
          <Button variant="primary" icon={<Pause className="h-4 w-4" />} disabled={!project}
            onClick={() => project && panels.open('pause', pauseProps(project.id))} title="Pause Session (Alt+Shift+P)" aria-label="Pause Session">
            <span className="hidden sm:inline">Pause Session</span><span className="sm:hidden">Pause</span></Button>
          <Button variant="ghost" size="sm" onClick={toggleTheme} aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}>
            {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
          <Button variant="ghost" size="sm" onClick={signOut} aria-label="Sign out" title={`Signed in as ${me?.email}`}><LogOut className="h-4 w-4" /></Button>
        </div>
      </header>
      <div className="flex min-h-0 flex-1">
        <aside className={cx('hidden shrink-0 border-r border-line bg-surface transition-[width] lg:block', collapsed ? 'w-[64px]' : 'w-[232px]')}>{sidebar}</aside>
        {mobileOpen && (
          <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
            <div className="absolute inset-0 bg-black/40" onClick={() => setMobileOpen(false)} />
            <aside className="absolute inset-y-0 left-0 w-[260px] bg-surface shadow-xl">
              <button className="absolute right-2 top-2 rounded p-2" onClick={() => setMobileOpen(false)} aria-label="Close menu"><X className="h-5 w-5" /></button>
              <div className="pt-10">{sidebar}</div>
            </aside>
          </div>
        )}
        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1180px] px-4 py-6 sm:px-6 lg:px-8">{children}</div>
        </main>
        <PanelHost />
      </div>
      <div className="pointer-events-none fixed bottom-4 left-1/2 z-50 flex w-[min(92vw,420px)] -translate-x-1/2 flex-col gap-2" aria-live="polite">
        {toasts.map(t => (
          <div key={t.id} className={cx('pointer-events-auto flex items-center gap-3 rounded-lg border px-4 py-3 text-sm shadow-lg',
            t.tone === 'error' ? 'border-danger/40 bg-danger-bg text-danger' : 'border-line bg-surface text-ink')}>
            <span className="flex-1">{t.text}</span>
            {t.action && <button className="font-semibold text-fact underline" onClick={() => { t.action!.run(); dismissToast(t.id) }}>{t.action.label}</button>}
            <button onClick={() => dismissToast(t.id)} aria-label="Dismiss"><X className="h-4 w-4" /></button>
          </div>
        ))}
      </div>
    </div>
  )
}
