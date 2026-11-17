/** Feature 6 — Complete Activity History (list, timeline and calendar views) + checkpoint timeline (5B). */
import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarDays, ChevronLeft, ChevronRight, List, Search, Trash2 } from 'lucide-react'
import { del, get, post } from '../api/client'
import type { Provenance } from '../api/types'
import { Button, Card, Empty, Input, Label, PageHeader, Pill, ProvBadge, Spinner, cx, fmtTime, shortUrl } from '../components/ui'
import { useApp } from '../state/app'
import { usePanels } from '../state/panels'
import { CheckpointSlider } from './Resume'

interface Item { kind: string; group: string; id: number; project_id: number | null; project: string | null; title: string; url?: string; detail?: string; at: string; provenance: Provenance }
const tz = -new Date().getTimezoneOffset()
const KINDS = [['work', 'Work sessions'], ['checkpoint', 'Checkpoints'], ['thought', 'Thoughts'], ['source', 'Selected sources'], ['browser', 'Browser metadata']] as const

export function HistoryPage() {
  const { project, projects, toast } = useApp()
  const panels = usePanels()
  const qc = useQueryClient()
  const [view, setView] = useState<'list' | 'calendar'>('list')
  const [q, setQ] = useState(''), [site, setSite] = useState('')
  const [pid, setPid] = useState<number | ''>(project?.id ?? '')
  const [from, setFrom] = useState(''), [to, setTo] = useState('')
  const [kinds, setKinds] = useState<string[]>(KINDS.map(k => k[0]))
  const params = new URLSearchParams({ q, website: site, kinds: kinds.join(','), tz_offset_minutes: String(tz), ...(pid ? { project_id: String(pid) } : {}), ...(from ? { date_from: from } : {}), ...(to ? { date_to: to } : {}) })
  const list = useQuery({ queryKey: ['history', params.toString()], queryFn: () => get<{ items: Item[] }>(`/api/history?${params}`) })

  const grouped = useMemo(() => {
    const g: Record<string, Item[]> = {}
    for (const i of list.data?.items ?? []) { const d = new Date(i.at).toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' }); (g[d] ||= []).push(i) }
    return Object.entries(g)
  }, [list.data])

  const open = (i: Item) => {
    if (i.kind === 'checkpoint') panels.open('checkpoint', { checkpointId: i.id })
    else if (i.kind === 'thought' && i.project_id) panels.open('thought', { projectId: i.project_id, thoughtId: i.id })
    else if (i.url) panels.open('source', { title: i.title, url: i.url, kind: i.group })
  }
  const remove = async (i: Item) => { await del(`/api/activity/${i.id}`); qc.invalidateQueries({ queryKey: ['history'] }); toast('Record deleted.') }
  const clearRange = async () => {
    if (!from || !to) { toast('Choose a From and To date first.', 'info'); return }
    if (!confirm(`Delete all browser metadata from ${from} to ${to}? Checkpoints, thoughts and notes are kept.`)) return
    const start = new Date(from + 'T00:00').toISOString(), end = new Date(to + 'T23:59:59').toISOString()
    const r = await post('/api/history/clear', { start, end, kinds: ['browser'] }); qc.invalidateQueries(); toast(`Removed ${r.removed.browser ?? 0} browser records.`)
  }

  return (
    <div>
      <PageHeader title="History & Timeline" sub="Your recorded work sessions and browser metadata, kept clearly apart."
        actions={<div className="flex gap-1" role="group" aria-label="View">
          <Button size="sm" variant={view === 'list' ? 'selected' : 'secondary'} icon={<List className="h-4 w-4" />} onClick={() => setView('list')}>Timeline</Button>
          <Button size="sm" variant={view === 'calendar' ? 'selected' : 'secondary'} icon={<CalendarDays className="h-4 w-4" />} onClick={() => setView('calendar')}>Calendar</Button>
        </div>} />

      {project && <Card className="mb-4 p-4"><div className="mb-1 text-[13px] font-semibold">Checkpoint timeline — {project.name}</div>
        <CheckpointSlider projectId={project.id} value={null} onChange={id => panels.open('checkpoint', { checkpointId: id })} />
        <p className="text-[12px] text-muted">Drag to open any checkpoint. Viewing older checkpoints never removes newer ones.</p></Card>}

      <Card className="mb-4 grid gap-3 p-4 md:grid-cols-6">
        <div className="md:col-span-2"><Label htmlFor="h-q">Keyword</Label><div className="relative"><Search className="absolute left-3 top-3 h-4 w-4 text-muted" /><Input id="h-q" className="pl-9" value={q} onChange={e => setQ(e.target.value)} /></div></div>
        <div><Label htmlFor="h-p">Project</Label><select id="h-p" value={pid} onChange={e => setPid(e.target.value ? Number(e.target.value) : '')} className="h-10 w-full rounded-md border border-line bg-surface px-2 text-sm"><option value="">All</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></div>
        <div><Label htmlFor="h-s">Website</Label><Input id="h-s" value={site} onChange={e => setSite(e.target.value)} placeholder="e.g. nature.com" /></div>
        <div><Label htmlFor="h-f">From</Label><Input id="h-f" type="date" value={from} onChange={e => setFrom(e.target.value)} /></div>
        <div><Label htmlFor="h-t">To</Label><Input id="h-t" type="date" value={to} onChange={e => setTo(e.target.value)} /></div>
        <div className="flex flex-wrap items-center gap-3 md:col-span-6">
          {KINDS.map(([k, label]) => (
            <label key={k} className="flex items-center gap-1.5 text-[13px]"><input type="checkbox" className="accent-[rgb(var(--navy))]" checked={kinds.includes(k)} onChange={e => setKinds(e.target.checked ? [...kinds, k] : kinds.filter(x => x !== k))} />{label}</label>
          ))}
          <Button size="sm" variant="danger" className="ml-auto" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={clearRange}>Clear browser history in range</Button>
        </div>
      </Card>

      {view === 'calendar' ? <CalendarView projectId={pid || null} onPick={d => { setFrom(d); setTo(d); setView('list') }} /> : !list.data ? <Spinner /> : grouped.length === 0 ? <Empty title="Nothing matches these filters" /> : (
        <div className="space-y-6">
          {grouped.map(([day, items]) => (
            <section key={day}>
              <h2 className="mb-2 text-[13px] font-semibold text-muted">{day}</h2>
              <ol className="relative space-y-2 border-l-2 border-line pl-5">
                {items.map(i => (
                  <li key={i.kind + i.id} className="relative">
                    <span className={cx('absolute -left-[27px] top-3.5 h-3 w-3 rounded-full border-2 border-surface', i.kind === 'browser' ? 'bg-excl' : 'bg-fact')} aria-hidden />
                    <Card className="flex flex-wrap items-center gap-3 p-3">
                      <Pill tone={i.group === 'Browser metadata' ? 'gray' : 'blue'}>{i.group}</Pill>
                      <button onClick={() => open(i)} className="min-w-0 flex-1 text-left">
                        <div className="truncate text-sm font-medium hover:text-fact">{i.title}</div>
                        <div className="truncate text-[12px] text-muted">{i.url ? shortUrl(i.url) : i.detail}{i.project && ` · ${i.project}`}</div>
                      </button>
                      <ProvBadge kind={i.provenance} />
                      <span className="text-[12px] text-muted">{fmtTime(i.at)}</span>
                      {i.kind === 'browser' && <Button size="sm" variant="ghost" onClick={() => remove(i)} aria-label="Delete this record"><Trash2 className="h-4 w-4" /></Button>}
                    </Card>
                  </li>
                ))}
              </ol>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}

function CalendarView({ projectId, onPick }: { projectId: number | null; onPick: (d: string) => void }) {
  const [month, setMonth] = useState(() => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}` })
  const q = useQuery({ queryKey: ['calendar', month, projectId], queryFn: () => get<{ days: { date: string; work: number; browser: number }[] }>(`/api/history/calendar?month=${month}&tz_offset_minutes=${tz}${projectId ? `&project_id=${projectId}` : ''}`) })
  const [y, m] = month.split('-').map(Number)
  const first = new Date(y, m - 1, 1), days = new Date(y, m, 0).getDate()
  const lead = (first.getDay() + 6) % 7
  const byDate = Object.fromEntries((q.data?.days ?? []).map(d => [d.date, d]))
  const shift = (n: number) => { const d = new Date(y, m - 1 + n, 1); setMonth(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`) }
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <Button size="sm" variant="ghost" onClick={() => shift(-1)} aria-label="Previous month"><ChevronLeft className="h-4 w-4" /></Button>
        <div className="font-semibold">{first.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}</div>
        <Button size="sm" variant="ghost" onClick={() => shift(1)} aria-label="Next month"><ChevronRight className="h-4 w-4" /></Button>
      </div>
      <div className="grid grid-cols-7 gap-1 text-center text-[12px] text-muted">{['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(d => <div key={d}>{d}</div>)}</div>
      <div className="mt-1 grid grid-cols-7 gap-1">
        {Array.from({ length: lead }).map((_, i) => <div key={'l' + i} />)}
        {Array.from({ length: days }).map((_, i) => {
          const date = `${month}-${String(i + 1).padStart(2, '0')}`; const d = byDate[date]
          return (
            <button key={date} onClick={() => onPick(date)} className={cx('min-h-[64px] rounded-md border p-1.5 text-left text-[12px] hover:border-fact', d ? 'border-line bg-surface' : 'border-transparent bg-canvas')}
              aria-label={`${date}: ${d?.work ?? 0} work records, ${d?.browser ?? 0} browser records`}>
              <div className="font-semibold">{i + 1}</div>
              {d?.work ? <div className="text-fact">● {d.work} work</div> : null}
              {d?.browser ? <div className="text-muted">○ {d.browser} browser</div> : null}
            </button>
          )
        })}
      </div>
    </Card>
  )
}
