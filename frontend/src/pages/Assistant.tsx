/** AI Assistant: Connect My Research (21), suggestion history with Why?, and the next-step task tracker (22). */
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, CircleHelp, Network, Pin, PinOff, Plus, X } from 'lucide-react'
import { del, get, patch, post } from '../api/client'
import type { Suggestion, Task } from '../api/types'
import { Button, Card, Empty, Input, PageHeader, Pill, ProvBadge, ProvBox, SectionTitle, Spinner, fmtTime } from '../components/ui'
import { useApp } from '../state/app'
import { usePanels } from '../state/panels'

interface Connection { theme: string; explanation: string; missing: string; next_step: string; evidence: { ref: string; type_label: string; label: string; url: string | null; excerpt: string }[] }

export function AssistantPage() {
  const { project, toast } = useApp()
  const panels = usePanels()
  const qc = useQueryClient()
  const [conn, setConn] = useState<{ connections: Connection[]; provider: string; evidence_considered: number } | null>(null)
  const [busy, setBusy] = useState(false)
  const [newTask, setNewTask] = useState('')
  const [status, setStatus] = useState<'open' | 'all'>('open')
  const tasks = useQuery({ queryKey: ['tasks', project?.id, status], enabled: !!project, queryFn: () => get<{ tasks: Task[] }>(`/api/tasks?project_id=${project!.id}&status=${status}`) })
  const sugg = useQuery({ queryKey: ['suggestions', project?.id], enabled: !!project, queryFn: () => get<{ suggestions: Suggestion[] }>(`/api/projects/${project!.id}/suggestions`) })
  if (!project) return <Empty title="No project selected" />

  const connect = async () => { setBusy(true); try { setConn(await post(`/api/projects/${project.id}/connect-research`)) } catch (e: any) { toast(e.message, 'error') } finally { setBusy(false) } }
  const toTask = async (s: Suggestion) => { await post('/api/tasks', { project_id: project.id, title: s.display_text, suggestion_id: s.id, checkpoint_id: s.checkpoint_id }); qc.invalidateQueries(); toast('Added to tasks.') }
  const setTask = async (t: Task, body: any) => { await patch(`/api/tasks/${t.id}`, body); qc.invalidateQueries() }

  return (
    <div className="space-y-6">
      <PageHeader title="AI Assistant" sub="Suggestions are always labelled, explained, and yours to accept, correct or reject." />

      <Card className="p-5">
        <SectionTitle action={<Button variant="primary" icon={<Network className="h-4 w-4" />} loading={busy} onClick={connect}>Connect my research</Button>}>Connect My Research</SectionTitle>
        <p className="text-sm text-muted">Finds themes, overlaps and gaps across your notes, thoughts and selected sources. It only uses what you approved, and each connection lists its evidence.</p>
        {conn && (
          <div className="mt-4 space-y-3">
            <p className="text-[12px] text-muted">Looked at {conn.evidence_considered} approved items · {conn.provider === 'placeholder' ? 'Placeholder AI (no API key)' : 'OpenAI'}</p>
            {conn.connections.length === 0 && <p className="text-sm">Not enough overlapping material yet. Add a few notes or references and try again.</p>}
            {conn.connections.map((c, i) => (
              <ProvBox key={i} kind="ai_suggestion" title={c.theme}>
                <p>{c.explanation}</p>
                {c.missing && <p className="mt-1"><span className="text-muted">Possibly missing:</span> {c.missing}</p>}
                {c.next_step && <p className="mt-1"><span className="text-muted">Possible next research step:</span> {c.next_step}</p>}
                <div className="mt-2 text-[12px] font-semibold text-muted">Evidence</div>
                <ul className="mt-1 space-y-1 text-[13px]">{c.evidence.map(e => <li key={e.ref}>• <span className="text-muted">{e.type_label}:</span> {e.url ? <a className="text-fact underline" href={e.url} target="_blank" rel="noopener noreferrer">{e.label}</a> : e.label}</li>)}</ul>
              </ProvBox>
            ))}
          </div>
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <SectionTitle action={<div className="flex gap-1"><Button size="sm" variant={status === 'open' ? 'selected' : 'secondary'} onClick={() => setStatus('open')}>Open</Button><Button size="sm" variant={status === 'all' ? 'selected' : 'secondary'} onClick={() => setStatus('all')}>All</Button></div>}>Next-step tasks</SectionTitle>
          <form className="mb-3 flex gap-2" onSubmit={async e => { e.preventDefault(); if (!newTask.trim()) return; await post('/api/tasks', { project_id: project.id, title: newTask }); setNewTask(''); qc.invalidateQueries() }}>
            <Input aria-label="New task" value={newTask} onChange={e => setNewTask(e.target.value)} placeholder="Add your own task" /><Button type="submit" icon={<Plus className="h-4 w-4" />}>Add</Button>
          </form>
          {!tasks.data ? <Spinner /> : tasks.data.tasks.length === 0 ? <p className="text-sm text-muted">No tasks.</p> : (
            <ul className="divide-y divide-line">
              {tasks.data.tasks.map(t => (
                <li key={t.id} className="flex items-center gap-2 py-2">
                  <button onClick={() => setTask(t, { status: t.status === 'done' ? 'open' : 'done' })} aria-label={t.status === 'done' ? 'Mark open' : 'Mark completed'}><CheckCircle2 className={t.status === 'done' ? 'h-5 w-5 text-ok' : 'h-5 w-5 text-excl'} /></button>
                  <span className={'min-w-0 flex-1 text-sm ' + (t.status !== 'open' ? 'text-muted line-through' : '')}
                    contentEditable={t.status === 'open'} suppressContentEditableWarning aria-label="Edit task"
                    onBlur={e => { const v = e.currentTarget.textContent?.trim(); if (v && v !== t.title) setTask(t, { title: v }) }}>{t.title}</span>
                  <ProvBadge kind={t.provenance} />
                  <button onClick={async () => { t.pinned ? await del(`/api/pins/task/${t.id}`) : await post('/api/pins', { item_type: 'task', item_id: t.id, project_id: project.id }); qc.invalidateQueries() }} aria-label={t.pinned ? 'Unpin task' : 'Pin task'}>{t.pinned ? <PinOff className="h-4 w-4" /> : <Pin className="h-4 w-4 text-muted" />}</button>
                  {t.status === 'open' && <button onClick={() => setTask(t, { status: 'dismissed' })} aria-label="Dismiss task"><X className="h-4 w-4 text-muted" /></button>}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="p-5">
          <SectionTitle>Suggestion history</SectionTitle>
          {!sugg.data ? <Spinner /> : sugg.data.suggestions.length === 0 ? <p className="text-sm text-muted">No suggestions yet. Open the Resume Workspace after a checkpoint.</p> : (
            <ul className="space-y-2">
              {sugg.data.suggestions.slice(0, 12).map(s => (
                <li key={s.id} className="rounded-md border border-line p-3 text-sm">
                  <div className="mb-1 flex flex-wrap items-center gap-2"><ProvBadge kind={s.provenance} /><Pill>{s.kind === 'next_step' ? 'Next step' : 'Context guess'}</Pill><Pill tone={s.status === 'rejected' ? 'red' : s.status === 'pending' ? 'gray' : 'green'}>{s.status}</Pill><span className="text-[12px] text-muted">{fmtTime(s.created_at)}</span></div>
                  <p className={s.status === 'rejected' && !s.user_text ? 'text-muted line-through' : ''}>{s.display_text ?? s.ai_text ?? 'Rejected guess (hidden)'}</p>
                  <div className="mt-2 flex gap-2">
                    <Button size="sm" icon={<CircleHelp className="h-3.5 w-3.5" />} onClick={() => panels.open('why', { suggestionId: s.id })}>Why?</Button>
                    {s.status === 'pending' && <Button size="sm" onClick={() => panels.open('review', { suggestionId: s.id })}>Review</Button>}
                    {s.kind === 'next_step' && s.display_text && <Button size="sm" onClick={() => toTask(s)}>Make it a task</Button>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}
