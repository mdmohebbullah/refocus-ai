import { useEffect, useLayoutEffect, useRef } from 'react'
import { ArrowLeft, ArrowRight, X } from 'lucide-react'
import { usePanels } from '../state/panels'
import { PANELS } from '../panels'
import { cx } from './ui'

/** Right-hand panel with browser-like ← Back / Forward → (Feature 5A). */
export function PanelHost() {
  const p = usePanels()
  const body = useRef<HTMLDivElement>(null)
  const scrolls = useRef<Record<string, number>>({})
  const cur = p.current

  // Each panel remembers its own scroll position; returning to it restores the position.
  useLayoutEffect(() => {
    if (body.current && cur) body.current.scrollTop = scrolls.current[cur.key] ?? 0
  }, [cur?.key]) // eslint-disable-line react-hooks/exhaustive-deps

  const remember = () => { if (body.current && cur) scrolls.current[cur.key] = body.current.scrollTop }

  useEffect(() => {
    if (!cur) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') p.close() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [cur, p])

  if (!cur) return null
  const def = PANELS[cur.type]
  const Body = def.component
  return (
    <aside role="dialog" aria-label={def.title(cur.props)}
      className="fixed inset-0 z-30 flex flex-col bg-surface md:static md:inset-auto md:z-auto md:w-[460px] md:shrink-0 md:border-l md:border-line">
      <div className="flex h-14 shrink-0 items-center gap-1 border-b border-line px-2">
        <button onClick={p.back} disabled={!p.canBack} aria-label="Back to previous panel" title="Back (Alt+Shift+←)"
          className="flex h-9 items-center gap-1 rounded-md px-2 text-sm font-medium text-ink hover:bg-canvas disabled:opacity-35">
          <ArrowLeft className="h-4 w-4" /> Back
        </button>
        <button onClick={p.forward} disabled={!p.canForward} aria-label="Forward to next panel" title="Forward (Alt+Shift+→)"
          className="flex h-9 items-center gap-1 rounded-md px-2 text-sm font-medium text-ink hover:bg-canvas disabled:opacity-35">
          Forward <ArrowRight className="h-4 w-4" />
        </button>
        <div className="min-w-0 flex-1 px-2 text-center">
          <div className="truncate text-sm font-semibold">{def.title(cur.props)}</div>
          {p.position.total > 1 && <div className="text-[11px] text-muted">Panel {p.position.index} of {p.position.total}</div>}
        </div>
        <button onClick={p.close} className="rounded-md p-2 hover:bg-canvas" aria-label="Close panel"><X className="h-4 w-4" /></button>
      </div>
      <div ref={body} onScroll={remember} className={cx('min-h-0 flex-1 overflow-y-auto p-5')}>
        <Body key={cur.key} {...cur.props} />
      </div>
    </aside>
  )
}
