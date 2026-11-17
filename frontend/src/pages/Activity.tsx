/** Feature 4 — Last 60 Minutes, plus Time Away (15) and Active Work Time (16). */
import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import { del, get, patch, post } from '../api/client'
import type { Activity, TimeStatus } from '../api/types'
import { Button, Card, Empty, Input, Label, PageHeader, Pill, SectionTitle, Spinner, cx, fmtDuration, fmtMinutes, fmtTime, shortUrl } from '../components/ui'
import { useApp } from '../state/app'

const WINDOWS = [15, 30, 60] as const
const tz = -new Date().getTimezoneOffset()

export function ActivityPage() {
  const { project, projects, toast } = useApp()
  const qc = useQueryClient()
  const [win, setWin] = useState<number | 'custom'>(60)
  const [cStart, setCStart] = useState(''), [cEnd, setCEnd] = useState('')
  const url = win === 'custom'
    ? (cStart && cEnd ? `/api/activity?start=${new Date(cStart).toISOString()}&end=${new Date(cEnd).toISOString()}` : null)
    : `/api/activity?minutes=${win}`
  const act = useQuery({ queryKey: ['activity', url], enabled: !!url, queryFn: () => get<{ events: Activity[]; note: string; start: string; end: string }>(url!), refetchInterval: 30_000 })
  const time = useQuery({ queryKey: ['time', project?.id], enabled: !!project, queryFn: () => get<TimeStatus>(`/api/time/status?project_id=${project!.id}`), refetchInterval: 30_000 })
  const week = useQuery({ queryKey: ['time-week', project?.id], enabled: !!project,
    queryFn: () => get<{ days: { date: string; active_seconds: number; away_seconds: number }[]; total_active_seconds: number }>(`/api/time/summary?project_id=${project!.id}&days=7&tz_offset_minutes=${tz}`) })
  const records = useQuery({ queryKey: ['time-records', project?.id], enabled: !!project,
    queryFn: () => get<{ records: { id: number; kind: string; started_at: string; ended_at: string; seconds: number; source: string; corrected: boolean; note: string }[] }>(`/api/time/records?project_id=${project!.id}&limit=12`) })

  const events = act.data?.events ?? []
  const points = useMemo(() => events.filter(e => !e.excluded).map(e => ({ x: new Date(e.occurred_at).getTime(), y: e.selected ? 1 : 0, id: e.id, title: e.title })), [events])

  const select = async (ids: number[], selected: boolean) => { await post('/api/activity/select', { ids, selected }); qc.invalidateQueries({ queryKey: ['activity'] }) }
  const assign = async (id: number, pid: number | null) => { await post('/api/activity/assign', { ids: [id], project_id: pid }); qc.invalidateQueries({ queryKey: ['activity'] }) }
  const remove = async (id: number) => { await del(`/api/activity/${id}`); qc.invalidateQueries({ queryKey: ['activity'] }) }

  return (
    <div className="space-y-6">
      <PageHeader title="Recent Activity" sub="What Re-Focus AI recorded from your browser, and how long you've been working." />

      {project && time.data && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {[
            ['Active work time', fmtDuration(time.data.total_recorded_seconds), 'total recorded for this project'],
            ['Current session', fmtDuration(time.data.current_session_seconds), time.data.active_now ? 'active now' : 'not active'],
            ['Time away', time.data.active_now ? '—' : fmtMinutes(time.data.minutes_away), 'from this project'],
            ['Last active', fmtTime(time.data.last_active_at), ''],
            ['Suggested help level', time.data.suggested_help_level, time.data.recommended_resume],
          ].map(([k, v, s]) => (
            <Card key={k} className="p-4"><div className="text-[12px] text-muted">{k}</div><div className="mt-1 text-lg font-semibold capitalize">{v}</div>{s && <div className="text-[12px] text-muted">{s}</div>}</Card>
          ))}
        </div>
      )}
      {time.data && <p className="-mt-3 text-[12px] text-muted">{time.data.basis} Unattended background tabs never count as active work.</p>}

      <Card className="p-4">
        <SectionTitle action={
          <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Time window">
            {WINDOWS.map(w => <Button key={w} size="sm" variant={win === w ? 'selected' : 'secondary'} onClick={() => setWin(w)}>Last {w} min</Button>)}
            <Button size="sm" variant={win === 'custom' ? 'selected' : 'secondary'} onClick={() => setWin('custom')}>Custom</Button>
          </div>}>Last 60 Minutes</SectionTitle>
        {win === 'custom' && (
          <div className="mb-3 flex flex-wrap gap-3">
            <div><Label htmlFor="c-start">From</Label><Input id="c-start" type="datetime-local" value={cStart} onChange={e => setCStart(e.target.value)} /></div>
            <div><Label htmlFor="c-end">To</Label><Input id="c-end" type="datetime-local" value={cEnd} onChange={e => setCEnd(e.target.value)} /></div>
          </div>
        )}
        {act.data && <p className="mb-3 text-[12px] text-muted">{act.data.note}</p>}
        {!act.data ? (url ? <Spinner /> : <p className="text-sm text-muted">Choose a start and end time.</p>) : events.length === 0 ? (
          <Empty title="No browser activity in this window">Pair the extension in Settings to see visited pages here.</Empty>
        ) : (
          <>
            <div className="h-40" aria-label="Activity timeline: each dot is a visited page; top row is selected for AI">
              <ResponsiveContainer>
                <ScatterChart margin={{ left: 0, right: 16, top: 10, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" />
                  <XAxis type="number" dataKey="x" domain={[new Date(act.data.start).getTime(), new Date(act.data.end).getTime()]} scale="time"
                    tickFormatter={v => new Date(v).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })} fontSize={11} stroke="rgb(var(--muted))" />
                  <YAxis type="number" dataKey="y" domain={[-0.5, 1.5]} ticks={[0, 1]} tickFormatter={v => (v ? 'Selected' : 'Not used')} width={70} fontSize={11} stroke="rgb(var(--muted))" />
                  <ZAxis range={[70, 70]} />
                  <Tooltip cursor={false} content={({ payload }) => payload?.[0] ? <div className="rounded border border-line bg-surface px-2 py-1 text-[12px]">{(payload[0].payload as any).title}<br />{fmtTime(new Date((payload[0].payload as any).x).toISOString())}</div> : null} />
                  <Scatter data={points} fill="rgb(var(--fact))" onClick={(d: any) => select([d.id], !d.y)} cursor="pointer" />
                </ScatterChart>
              </ResponsiveContainer>
            </div>
            <div className="my-3 flex gap-2">
              <Button size="sm" onClick={() => select(events.filter(e => !e.excluded).map(e => e.id), true)}>Let AI consider all</Button>
              <Button size="sm" onClick={() => select(events.filter(e => !e.excluded).map(e => e.id), false)}>Consider none</Button>
            </div>
            <ol className="divide-y divide-line">
              {events.map(e => (
                <li key={e.id} className={cx('flex flex-wrap items-center gap-3 py-2.5', e.excluded && 'opacity-60')}>
                  <span className="w-16 shrink-0 text-[12px] tabular-nums text-muted">{new Date(e.occurred_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</span>
                  <input type="checkbox" className="h-4 w-4 accent-[rgb(var(--navy))]" aria-label={`AI may consider “${e.title ?? 'excluded page'}”`}
                    disabled={e.excluded} checked={e.selected} onChange={x => select([e.id], x.target.checked)} />
                  <div className="min-w-0 flex-1"><div className="truncate text-sm">{e.excluded ? 'Excluded website' : e.title}</div><div className="truncate text-[12px] text-muted">{e.excluded ? e.domain : shortUrl(e.url)}</div></div>
                  <Pill tone={e.excluded ? 'gray' : e.selected ? 'blue' : 'neutral'}>{e.excluded ? 'Excluded' : e.selected ? 'Selected' : 'Not used'}</Pill>
                  {!e.excluded && (
                    <select aria-label="Associated project" value={e.project_id ?? ''} onChange={x => assign(e.id, x.target.value ? Number(x.target.value) : null)} className="h-8 max-w-[160px] rounded border border-line bg-surface px-1 text-[12px]">
                      <option value="">No project</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </select>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => remove(e.id)} aria-label="Delete this record">Delete</Button>
                </li>
              ))}
            </ol>
          </>
        )}
      </Card>

      {project && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card className="p-4">
            <SectionTitle>This week</SectionTitle>
            {week.data && week.data.days.some(d => d.active_seconds || d.away_seconds) ? (
              <div className="h-56">
                <ResponsiveContainer>
                  <BarChart data={week.data.days.map(d => ({ day: new Date(d.date + 'T12:00').toLocaleDateString([], { weekday: 'short' }), Active: Math.round(d.active_seconds / 60), Away: Math.round(d.away_seconds / 60) }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" vertical={false} />
                    <XAxis dataKey="day" fontSize={12} stroke="rgb(var(--muted))" /><YAxis fontSize={12} stroke="rgb(var(--muted))" unit=" m" width={44} />
                    <Tooltip /><Legend />
                    <Bar dataKey="Active" fill="rgb(var(--ok))" radius={[3, 3, 0, 0]} />
                    <Bar dataKey="Away" fill="rgb(var(--excl))" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : <p className="text-sm text-muted">No recorded time yet this week.</p>}
            {week.data && <p className="mt-2 text-[13px] text-muted">Active this week: <strong className="text-ink">{fmtDuration(week.data.total_active_seconds)}</strong></p>}
          </Card>
          <Card className="p-4">
            <SectionTitle>Recent time records</SectionTitle>
            <ManualTime projectId={project.id} onSaved={() => { qc.invalidateQueries(); toast('Time record added.') }} />
            <ul className="mt-3 divide-y divide-line text-[13px]">
              {records.data?.records.map(r => (
                <li key={r.id} className="flex items-center gap-2 py-1.5">
                  <Pill tone={r.kind === 'active' ? 'green' : 'gray'}>{r.kind}</Pill>
                  <span className="flex-1">{fmtTime(r.started_at)} · {fmtDuration(r.seconds)}{r.corrected && <span className="text-muted"> · corrected</span>}</span>
                  <button className="text-[12px] text-fact underline" onClick={async () => { await patch(`/api/time/records/${r.id}`, { kind: r.kind === 'active' ? 'away' : 'active' }); qc.invalidateQueries() }}>
                    Mark {r.kind === 'active' ? 'away' : 'active'}
                  </button>
                  <button className="text-[12px] text-danger underline" onClick={async () => { await del(`/api/time/records/${r.id}`); qc.invalidateQueries() }}>Delete</button>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}
    </div>
  )
}

function ManualTime({ projectId, onSaved }: { projectId: number; onSaved: () => void }) {
  const [start, setStart] = useState(''), [end, setEnd] = useState(''), [note, setNote] = useState('')
  const save = async () => {
    await post('/api/time/records', { project_id: projectId, started_at: new Date(start).toISOString(), ended_at: new Date(end).toISOString(), kind: 'active', note })
    setStart(''); setEnd(''); setNote(''); onSaved()
  }
  return (
    <details className="rounded-md border border-line p-2">
      <summary className="cursor-pointer text-[13px] font-semibold">Add time the app couldn't see</summary>
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        <div><Label htmlFor="mt-s">Start</Label><Input id="mt-s" type="datetime-local" value={start} onChange={e => setStart(e.target.value)} /></div>
        <div><Label htmlFor="mt-e">End</Label><Input id="mt-e" type="datetime-local" value={end} onChange={e => setEnd(e.target.value)} /></div>
        <div className="sm:col-span-2"><Label htmlFor="mt-n">Note</Label><Input id="mt-n" value={note} onChange={e => setNote(e.target.value)} placeholder="e.g. writing on paper" /></div>
      </div>
      <Button size="sm" className="mt-2" variant="primary" disabled={!start || !end} onClick={save}>Add record</Button>
    </details>
  )
}
