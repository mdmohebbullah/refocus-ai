/** Scenario 1 — Pause and save context (Feature 7) + Question for Your Future Self (Feature 9). */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, SkipForward } from 'lucide-react'
import { get, post } from '../api/client'
import type { Activity, Note, Position, Project, Reference, Tab, Task, Thought, Doc } from '../api/types'
import { Button, Check, Input, Label, ProvBadge, Spinner, TextArea, cx, shortUrl } from '../components/ui'
import { editorBridge, useApp } from '../state/app'
import { usePanelState, usePanels } from '../state/panels'
import { VoiceButton } from '../components/VoiceButton'
import { useShortcutEvent } from '../hooks/useShortcuts'

interface Draft {
  project: Project; document: Doc | null; position: Position | null
  external_paragraphs: { index: number; text: string; heading_id?: string }[] | { error: string } | null
  goal: string; tabs: Tab[]; activity: Activity[]; thoughts: Thought[]; notes: Note[]; references: Reference[]; tasks: Task[]
  source_links: { title: string; url: string }[]
  future_self: { question: string; generated_by: string }
  browser_collection: string
}

function Group({ title, count, children }: { title: string; count?: number; children: React.ReactNode }) {
  return (
    <fieldset className="border-t border-line pt-3">
      <legend className="pr-2 text-[13px] font-semibold">{title}{count !== undefined && <span className="ml-1 font-normal text-muted">({count})</span>}</legend>
      <div className="mt-1">{children}</div>
    </fieldset>
  )
}

export interface PauseProps { projectId: number; docId?: number | null; pos?: { cursor: number; paragraph_text: string; paragraph_index: number } | null; openedAt?: number }

/** Captures the live editor position at the moment Pause is pressed. */
export function pauseProps(projectId: number): PauseProps {
  return { projectId, docId: editorBridge.docId, pos: editorBridge.getPosition?.() ?? null, openedAt: Date.now() }
}

export function PausePanel({ projectId, docId: openDocId, pos, openedAt }: PauseProps) {
  const { projects, toast } = useApp()
  const panels = usePanels()
  const qc = useQueryClient()
  const project = projects.find(p => p.id === projectId)

  const docId = openDocId ?? project?.documents?.[0]?.id ?? null
  const q = useQuery({
    queryKey: ['pause-draft', projectId, docId, openedAt],
    queryFn: () => get<Draft>(`/api/projects/${projectId}/pause-draft?` + new URLSearchParams({
      ...(docId ? { document_id: String(docId) } : {}),
      ...(pos ? { cursor: String(pos.cursor), paragraph_text: pos.paragraph_text, paragraph_index: String(pos.paragraph_index) } : {}),
    })),
    staleTime: Infinity,
  })

  const [unticked, setUnticked] = usePanelState<string[]>('unticked', [])
  const [goal, setGoal] = usePanelState<string | null>('goal', null)
  const [thinking, setThinking] = usePanelState('thinking', '')
  const [missing, setMissing] = usePanelState('missing', '')
  const [nextPlan, setNextPlan] = usePanelState('nextPlan', '')
  const [question, setQuestion] = usePanelState<string | null>('question', null)
  const [editingQ, setEditingQ] = usePanelState('editingQ', false)
  const [answer, setAnswer] = usePanelState('answer', '')
  const [skipped, setSkipped] = usePanelState('skipped', false)
  const [marked, setMarked] = usePanelState<number | null>('marked', null)
  const [saving, setSaving] = usePanelState('saving', false)

  const saveRef = { current: () => {} }
  useShortcutEvent('save_checkpoint', () => saveRef.current())
  if (q.isLoading || !q.data) return <Spinner label="Preparing your checkpoint" />
  const d = q.data
  const on = (k: string) => !unticked.includes(k)
  const flip = (k: string) => (v: boolean) => setUnticked(v ? unticked.filter(x => x !== k) : [...unticked, k])
  const goalText = goal ?? d.goal
  const qText = question ?? d.future_self.question
  const paragraphs = Array.isArray(d.external_paragraphs) ? d.external_paragraphs : null

  const save = async () => {
    setSaving(true)
    try {
      await editorBridge.flush?.()
      let position: Position | null = d.position
      if (paragraphs && marked !== null) {
        const p = paragraphs.find(x => x.index === marked)!
        position = { paragraph_index: p.index, paragraph_text: p.text, heading_id: p.heading_id ?? null, source: 'user_marked' }
      }
      const pick = (prefix: string, ids: number[]) => ids.filter(id => on(`${prefix}:${id}`))
      const cp = await post('/api/checkpoints', {
        project_id: projectId, document_id: d.document?.id ?? null, goal: goalText,
        position: position ? { ...position, provenance: undefined, provenance_label: undefined } : null,
        included: {
          include_position: on('position'), include_goal: on('goal'),
          tabs: pick('tab', d.tabs.map(t => t.id)), activity: pick('activity', d.activity.map(a => a.id)),
          thoughts: pick('thought', d.thoughts.map(t => t.id)), notes: pick('note', d.notes.map(n => n.id)),
          references: pick('reference', d.references.map(r => r.id)), tasks: pick('task', d.tasks.map(t => t.id)),
        },
        new_thought: (thinking || missing || nextPlan) ? { project_id: projectId, thinking, missing, next_plan: nextPlan, origin: 'typed' } : null,
        future_self: { question: qText, question_edited: question !== null && question !== d.future_self.question, answer: skipped ? '' : answer,
                       skipped: skipped || !answer.trim(), generated_by: d.future_self.generated_by },
      })
      await qc.invalidateQueries()
      toast('Checkpoint saved. Take your break — your thinking is kept.', 'ok', { label: 'View', run: () => panels.open('checkpoint', { checkpointId: cp.id }) })
      panels.close()
    } catch (e: any) {
      toast(e.message || 'Could not save the checkpoint', 'error')
      setSaving(false)
    }
  }

  saveRef.current = save
  return (
    <div className="space-y-4">
      <div>
        <p className="text-sm text-muted">Untick anything you don't need. Nothing is saved until you press <strong className="text-ink">Save checkpoint</strong>.</p>
      </div>

      <Group title="Current project and document">
        <div className="text-sm"><strong>{d.project.name}</strong>{d.document && <> · {d.document.title} {d.document.read_only && <span className="text-muted">({d.document.source === 'google_docs' ? 'Google Docs' : 'Word'}, read-only)</span>}</>}</div>
      </Group>

      {d.position && (
        <Group title="Exact writing position">
          <Check checked={on('position')} onChange={flip('position')}>
            <span className="block font-serif text-[14px] italic text-ink">“…{d.position.paragraph_text.slice(-140) || 'Start of document'}”</span>
            <ProvBadge kind="saved_by_you" extra="cursor position" />
          </Check>
        </Group>
      )}

      {paragraphs && (
        <Group title="Mark where you stopped">
          <p className="mb-2 text-[13px] text-muted">Re-Focus AI can't see your cursor in {d.document?.source === 'google_docs' ? 'Google Docs' : 'Word'}. Tap the paragraph where you stopped. If you skip this, an <em>AI Guess</em> will be used.</p>
          <div className="max-h-56 space-y-1 overflow-y-auto rounded-md border border-line p-1" role="radiogroup" aria-label="Paragraph where you stopped">
            {paragraphs.map(p => (
              <button key={p.index} role="radio" aria-checked={marked === p.index} onClick={() => setMarked(p.index)}
                className={cx('block w-full rounded px-2 py-1.5 text-left font-serif text-[13px]', marked === p.index ? 'bg-fact-bg ring-1 ring-fact' : 'hover:bg-canvas')}>
                {p.text.slice(0, 160)}{p.text.length > 160 && '…'}
              </button>
            ))}
          </div>
        </Group>
      )}
      {d.external_paragraphs && !paragraphs && <p className="text-[13px] text-danger">Couldn't read the connected document right now: {(d.external_paragraphs as any).error}. You can still save.</p>}

      <Group title="Current goal">
        <Check checked={on('goal')} onChange={flip('goal')}>
          <Input aria-label="Current goal" value={goalText} onChange={e => setGoal(e.target.value)} placeholder="What are you trying to finish?" disabled={!on('goal')} />
        </Check>
      </Group>

      <Group title="Selected browser tabs" count={d.tabs.length}>
        {d.tabs.length === 0 && <p className="text-[13px] text-muted">{d.browser_collection === 'on' ? 'No tabs selected. Choose tabs on the Browser Tabs page.' : `Browser collection is ${d.browser_collection}.`}</p>}
        {d.tabs.map(t => <Check key={t.id} checked={on(`tab:${t.id}`)} onChange={flip(`tab:${t.id}`)}>{t.title}<span className="block text-[12px] text-muted">{shortUrl(t.url)}</span></Check>)}
      </Group>

      <Group title="Recent approved activity (60 min)" count={d.activity.length}>
        {d.activity.length === 0 && <p className="text-[13px] text-muted">None recorded.</p>}
        {d.activity.slice(0, 8).map(a => <Check key={a.id} checked={on(`activity:${a.id}`)} onChange={flip(`activity:${a.id}`)}>{a.title}<span className="block text-[12px] text-muted">{shortUrl(a.url)}</span></Check>)}
      </Group>

      <Group title="Unfinished thought">
        <div className="space-y-2.5 rounded-lg border border-line p-3">
          <div><Label htmlFor="pz-think">What were you thinking?</Label>
            <div className="flex gap-2"><TextArea id="pz-think" rows={2} value={thinking} onChange={e => setThinking(e.target.value)} />
              <VoiceButton onText={t => setThinking((thinking ? thinking + ' ' : '') + t)} projectId={projectId} /></div></div>
          <div><Label htmlFor="pz-miss">What information is missing?</Label><TextArea id="pz-miss" rows={2} value={missing} onChange={e => setMissing(e.target.value)} /></div>
          <div><Label htmlFor="pz-next">What were you planning to do next?</Label><TextArea id="pz-next" rows={2} value={nextPlan} onChange={e => setNextPlan(e.target.value)} /></div>
          <p className="text-[12px] text-muted">Saved exactly as you type it — never rewritten by AI.</p>
        </div>
        {d.thoughts.map(t => (
          <Check key={t.id} checked={on(`thought:${t.id}`)} onChange={flip(`thought:${t.id}`)}>{t.thinking || t.next_plan || t.missing}</Check>
        ))}
      </Group>

      {(d.notes.length > 0 || d.references.length > 0 || d.tasks.length > 0) && (
        <Group title="Notes, references and open tasks">
          {d.notes.map(n => <Check key={`n${n.id}`} checked={on(`note:${n.id}`)} onChange={flip(`note:${n.id}`)}>Note: {n.title || n.body.slice(0, 60)}</Check>)}
          {d.references.map(r => <Check key={`r${r.id}`} checked={on(`reference:${r.id}`)} onChange={flip(`reference:${r.id}`)}>Reference: {r.title}{r.url && <span className="block text-[12px] text-muted">{shortUrl(r.url)}</span>}</Check>)}
          {d.tasks.map(t => <Check key={`t${t.id}`} checked={on(`task:${t.id}`)} onChange={flip(`task:${t.id}`)}>Task: {t.title}</Check>)}
        </Group>
      )}

      <div className="rounded-lg border-[1.5px] border-dashed border-guess/60 bg-guess-bg/60 p-3.5">
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="text-[13px] font-semibold">A question for your future self</span>
          <ProvBadge kind={question !== null && question !== d.future_self.question ? 'saved_by_you' : 'ai_suggestion'} />
        </div>
        {editingQ
          ? <Input aria-label="Edit question" value={qText} onChange={e => setQuestion(e.target.value)} onBlur={() => setEditingQ(false)} autoFocus />
          : <p className="text-[15px] font-medium">{qText}</p>}
        {!skipped ? (
          <>
            <Label htmlFor="pz-ans">Your answer</Label>
            <div className="flex gap-2">
              <TextArea id="pz-ans" rows={2} value={answer} onChange={e => setAnswer(e.target.value)} placeholder="A few words are enough" />
              <VoiceButton onText={t => setAnswer((answer ? answer + ' ' : '') + t)} projectId={projectId} />
            </div>
          </>
        ) : <p className="mt-2 text-[13px] text-muted">Skipped. The question won't be shown when you return.</p>}
        <div className="mt-2 flex gap-2">
          <Button size="sm" variant="ghost" icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => setEditingQ(true)}>Edit question</Button>
          <Button size="sm" variant="ghost" icon={<SkipForward className="h-3.5 w-3.5" />} onClick={() => setSkipped(!skipped)}>{skipped ? 'Answer instead' : 'Skip'}</Button>
        </div>
      </div>

      <div className="sticky bottom-0 -mx-5 flex justify-end gap-2 border-t border-line bg-surface px-5 py-3">
        <Button onClick={panels.close}>Cancel</Button>
        <Button variant="primary" onClick={save} loading={saving}>Save checkpoint</Button>
      </div>
    </div>
  )
}
