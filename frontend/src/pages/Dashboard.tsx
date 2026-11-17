/** Feature 1 — Smart Dashboard. The most prominent element is “Resume previous work”. */
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { AppWindow, CheckSquare, Clock3, Lightbulb, Play, Plus } from 'lucide-react'
import { get } from '../api/client'
import type { Activity, Checkpoint, Project, Suggestion, Task, Thought, TimeStatus } from '../api/types'
import { Button, Card, Empty, Pill, ProvBadge, ProvBox, SectionTitle, Spinner, fmtDuration, fmtMinutes, shortUrl, timeAgo } from '../components/ui'
import { usePanels } from '../state/panels'
import { useApp } from '../state/app'
import { NewProjectButton } from './Projects'

interface Dash {
  user: { name: string }; project: Project | null; recent_projects: Project[]
  browser: { state: string; devices: { id: number; name: string; last_seen_at: string | null }[] }
  last_checkpoint?: Checkpoint | null; current_thought?: Thought | null; goal?: { text: string } | null
  next_step?: Suggestion | null; recent_activity?: Activity[]; time?: TimeStatus
  recent_history?: { kind: string; id: number; title: string; at: string }[]; pending_tasks?: Task[]
}

const BROWSER: Record<string, { text: string; tone: 'green' | 'amber' | 'gray' | 'blue' }> = {
  connected: { text: 'Extension connected', tone: 'green' }, not_seen_recently: { text: 'Extension not seen recently', tone: 'amber' },
  not_connected: { text: 'Extension not connected', tone: 'gray' }, private_mode: { text: 'Private mode — nothing collected', tone: 'blue' },
  collection_off: { text: 'Browser collection is off', tone: 'gray' },
}

function greeting() { const h = new Date().getHours(); return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening' }

export function DashboardPage() {
  const q = useQuery({ queryKey: ['dashboard'], queryFn: () => get<Dash>('/api/dashboard') })
  const panels = usePanels()
  const nav = useNavigate()
  const { setProjectId } = useApp()
  if (!q.data) return <Spinner />
  const d = q.data
  const b = BROWSER[d.browser.state]

  if (!d.project) {
    return (
      <div className="mx-auto max-w-xl pt-10">
        <h1 className="font-hand text-[40px] font-bold leading-none">Welcome, {d.user.name}</h1>
        <p className="mt-2 text-muted">Create a project for the writing you're working on. Re-Focus AI will help you pick up where you left off after every interruption.</p>
        <div className="mt-6"><NewProjectButton variant="primary" size="lg" /></div>
      </div>
    )
  }
  const t = d.time!
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-hand text-[40px] font-bold leading-none">{greeting()}, {d.user.name.split(' ')[0]}</h1>
          <p className="text-sm text-muted">Current project: <Link to={`/projects/${d.project.id}`} className="font-semibold text-ink underline-offset-2 hover:underline">{d.project.name}</Link></p>
        </div>
        <div className="flex gap-2">
          <NewProjectButton label="Start new project" />
          <Button icon={<Lightbulb className="h-4 w-4" />} onClick={() => panels.open('thought', { projectId: d.project!.id })}>Quick capture</Button>
        </div>
      </div>

      {/* Hero: Resume previous work */}
      <Card className="overflow-hidden">
        <div className="grid gap-0 md:grid-cols-[1fr_300px]">
          <div className="space-y-3 p-6">
            <div className="text-sm text-muted">{d.last_checkpoint ? <>Last checkpoint {timeAgo(d.last_checkpoint.created_at)} · {d.last_checkpoint.label}</> : 'No checkpoint yet — your project data will be used.'}</div>
            {d.last_checkpoint?.position?.paragraph_text && (
              <p className="font-serif text-[17px] italic leading-relaxed">“…{d.last_checkpoint.position.paragraph_text.slice(-160)}”</p>
            )}
            <div className="flex flex-wrap gap-2 pt-1">
              <Button variant="primary" size="lg" icon={<Play className="h-5 w-5" />} onClick={() => nav('/resume')} className="text-[16px]">Resume previous work</Button>
              {d.last_checkpoint && <Button size="lg" onClick={() => panels.open('resume', { projectId: d.project!.id })}>Resume last session (quick view)</Button>}
            </div>
          </div>
          <div className="border-t border-line bg-canvas p-6 md:border-l md:border-t-0">
            <dl className="space-y-3 text-sm">
              <div><dt className="text-muted">Time away</dt><dd className="text-lg font-semibold">{t.active_now ? 'Active now' : fmtMinutes(t.minutes_away)}</dd></div>
              <div><dt className="text-muted">Active work time</dt><dd className="font-semibold">{fmtDuration(t.current_session_seconds)} this session · {fmtDuration(t.total_recorded_seconds)} total</dd></div>
              <div><dt className="text-muted">Suggested help level</dt><dd className="font-semibold capitalize">{t.help_level}</dd></div>
            </dl>
          </div>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {d.goal && <ProvBox kind="saved_by_you" title="Last saved goal">{d.goal.text}</ProvBox>}
          {d.current_thought
            ? <ProvBox kind="saved_by_you" title="Current unfinished thought" right={<button className="text-[13px] text-fact underline" onClick={() => panels.open('thought', { projectId: d.project!.id, thoughtId: d.current_thought!.id })}>Open</button>}>
                {d.current_thought.thinking || d.current_thought.next_plan}{d.current_thought.missing && <p className="mt-1 text-muted">Missing: {d.current_thought.missing}</p>}
              </ProvBox>
            : <Empty title="No unfinished thought" action={<Button size="sm" onClick={() => panels.open('thought', { projectId: d.project!.id })}>Capture a thought</Button>}>Park an idea before you leave so you can pick it up later.</Empty>}
          {d.next_step && d.next_step.display_text && (
            <ProvBox kind={d.next_step.provenance} title="Suggested next step" right={<button className="text-[13px] text-fact underline" onClick={() => panels.open('why', { suggestionId: d.next_step!.id })}>Why?</button>}>
              {d.next_step.display_text}
            </ProvBox>
          )}

          <Card className="p-4">
            <SectionTitle action={<Link to="/history" className="text-[13px] text-fact underline">All history</Link>}>Recent history</SectionTitle>
            {d.recent_history!.length === 0 ? <p className="text-sm text-muted">Nothing yet.</p> : (
              <ul className="divide-y divide-line">
                {d.recent_history!.map(h => (
                  <li key={h.kind + h.id}>
                    <button className="flex w-full items-center gap-3 py-2.5 text-left text-sm hover:text-fact"
                      onClick={() => panels.open(h.kind === 'checkpoint' ? 'checkpoint' : 'thought', h.kind === 'checkpoint' ? { checkpointId: h.id } : { projectId: d.project!.id, thoughtId: h.id })}>
                      <Pill tone={h.kind === 'checkpoint' ? 'blue' : 'neutral'}>{h.kind === 'checkpoint' ? 'Checkpoint' : 'Thought'}</Pill>
                      <span className="min-w-0 flex-1 truncate">{h.title}</span><span className="text-[12px] text-muted">{timeAgo(h.at)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="space-y-4">
          <Card className="p-4">
            <SectionTitle><span className="flex items-center gap-2"><CheckSquare className="h-4 w-4" />Pending tasks</span></SectionTitle>
            {d.pending_tasks!.length === 0 ? <p className="text-sm text-muted">No open tasks.</p> :
              <ul className="space-y-2">{d.pending_tasks!.map(t => <li key={t.id} className="text-sm">• {t.title} <ProvBadge kind={t.provenance} /></li>)}</ul>}
          </Card>
          <Card className="p-4">
            <SectionTitle action={<Link to="/tabs" className="text-[13px] text-fact underline">Manage</Link>}><span className="flex items-center gap-2"><AppWindow className="h-4 w-4" />Browser</span></SectionTitle>
            <Pill tone={b.tone}>{b.text}</Pill>
            <div className="mt-3 text-[13px] font-semibold">Recent approved activity</div>
            {d.recent_activity!.length === 0 ? <p className="text-[13px] text-muted">None.</p> : (
              <ul className="mt-1 space-y-1.5">{d.recent_activity!.map(a => <li key={a.id} className="text-[13px]"><div className="truncate">{a.title}</div><div className="text-[12px] text-muted">{shortUrl(a.url)} · {timeAgo(a.occurred_at)}</div></li>)}</ul>
            )}
          </Card>
          <Card className="p-4">
            <SectionTitle action={<Link to="/projects" className="text-[13px] text-fact underline">All</Link>}><span className="flex items-center gap-2"><Clock3 className="h-4 w-4" />Recent projects</span></SectionTitle>
            <ul className="space-y-1">
              {d.recent_projects.map(p => (
                <li key={p.id}><button onClick={() => { setProjectId(p.id); nav(`/projects/${p.id}`) }} className="flex w-full items-center gap-2 rounded px-1 py-1.5 text-left text-sm hover:bg-canvas">
                  {p.pinned && <span aria-label="Pinned">★</span>}<span className="min-w-0 flex-1 truncate">{p.name}</span><span className="text-[12px] text-muted">{timeAgo(p.last_active_at ?? p.updated_at)}</span></button></li>
              ))}
            </ul>
            <div className="mt-2"><NewProjectButton size="sm" variant="ghost" icon={<Plus className="h-3.5 w-3.5" />} label="New project" /></div>
          </Card>
        </div>
      </div>
    </div>
  )
}
