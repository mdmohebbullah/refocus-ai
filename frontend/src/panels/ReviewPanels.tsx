import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ExternalLink } from 'lucide-react'
import { get, patch, post } from '../api/client'
import type { Checkpoint, HelpLevel, Suggestion } from '../api/types'
import { ResumeCardView, useResume } from '../components/ResumeCardView'
import { Button, Label, Pill, ProvBadge, ProvBox, Spinner, TextArea, cx, shortUrl } from '../components/ui'
import { useApp } from '../state/app'
import { usePanelState, usePanels } from '../state/panels'

/* ----------------------------------------------------------------- Resume card (panel) */
export function ResumePanel({ projectId, checkpointId }: { projectId: number; checkpointId?: number | null }) {
  const [cp, setCp] = usePanelState<number | null>('checkpoint', checkpointId ?? null)
  return <ResumeCardView projectId={projectId} checkpointId={cp} onNavigateCheckpoint={setCp} compact />
}

/* ----------------------------------------------------------------- Why? (Scenario 4) */
const CERTAINTY: Record<string, { label: string; tone: 'green' | 'amber' | 'gray' }> = {
  high: { label: 'Strong link', tone: 'green' }, medium: { label: 'Possible link', tone: 'amber' }, low: { label: 'Weak link', tone: 'gray' },
}

export function WhyPanel({ suggestionId }: { suggestionId: number }) {
  const panels = usePanels()
  const q = useQuery({ queryKey: ['suggestion', suggestionId], queryFn: () => get<Suggestion>(`/api/suggestions/${suggestionId}`) })
  if (!q.data) return <Spinner />
  const s = q.data
  return (
    <div className="space-y-4">
      <ProvBox kind={s.provenance} title={s.kind === 'context_guess' ? 'The guess' : 'The suggestion'}>{s.display_text ?? <em>Rejected</em>}</ProvBox>
      <div>
        <h3 className="text-[15px] font-semibold">{s.clue_heading}</h3>
        <p className="text-[13px] text-muted">These are the saved items the suggestion is based on. It is not a record of the AI's internal reasoning.</p>
      </div>
      {s.clues.length === 0 && <p className="text-sm text-muted">No reliable clues were found, so this suggestion has little support. Treat it with care.</p>}
      <ol className="space-y-3">
        {s.clues.map(c => (
          <li key={c.ref} className="rounded-lg border border-line p-3.5">
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-navy text-[12px] font-bold text-[rgb(var(--on-navy))]">{c.rank}</span>
              <span className="text-[12px] font-semibold text-muted">{c.type_label}</span>
              <Pill tone={CERTAINTY[c.certainty].tone}>{CERTAINTY[c.certainty].label}</Pill>
            </div>
            <div className="text-[14px] font-semibold">{c.label}</div>
            <p className="mt-1 text-[13px]">{c.explanation}</p>
            {c.excerpt && <p className="mt-2 rounded bg-canvas px-2 py-1.5 font-serif text-[13px] text-muted">“{c.excerpt.slice(0, 220)}{c.excerpt.length > 220 && '…'}”</p>}
            {c.url && (
              <Button size="sm" className="mt-2" icon={<ExternalLink className="h-3.5 w-3.5" />}
                onClick={() => panels.open('source', { title: c.label, url: c.url, excerpt: c.excerpt, kind: c.type_label })}>Open source</Button>
            )}
          </li>
        ))}
      </ol>
    </div>
  )
}

/* ----------------------------------------------------------------- Source preview / list */
export function SourcePanel({ title, url, excerpt, kind, note, list, projectId, checkpointId }: {
  title?: string; url?: string | null; excerpt?: string; kind?: string; note?: string; list?: boolean; projectId?: number; checkpointId?: number | null
}) {
  const panels = usePanels()
  const resume = useResume(list ? projectId : undefined, checkpointId)
  if (list) {
    if (!resume.data) return <Spinner />
    const sources = resume.data.facts.sources
    return (
      <div className="space-y-2">
        {sources.length === 0 && <p className="text-sm text-muted">No sources were kept with this checkpoint.</p>}
        {sources.map((s, i) => (
          <button key={i} onClick={() => panels.open('source', { title: s.title, url: s.url, kind: s.provenance_label })}
            className="block w-full rounded-lg border border-line p-3 text-left hover:bg-canvas">
            <div className="text-sm font-semibold">{s.title || s.url}</div>
            <div className="mt-0.5 flex items-center gap-2 text-[12px] text-muted">{shortUrl(s.url)} <ProvBadge kind={s.provenance} /></div>
          </button>
        ))}
      </div>
    )
  }
  return (
    <div className="space-y-4">
      {kind && <div className="text-[12px] font-semibold text-muted">{kind}</div>}
      <h3 className="text-lg font-semibold">{title}</h3>
      {url && <p className="break-all text-[13px] text-muted">{url}</p>}
      {excerpt && <blockquote className="rounded-lg bg-canvas p-3 font-serif text-[14px]">“{excerpt}”</blockquote>}
      {note && <p className="text-[13px]">{note}</p>}
      {url ? (
        <a href={url} target="_blank" rel="noopener noreferrer"
          className="inline-flex h-10 items-center gap-2 rounded-md bg-navy px-4 text-sm font-semibold text-[rgb(var(--on-navy))]">
          <ExternalLink className="h-4 w-4" /> Open and keep reading
        </a>
      ) : <p className="text-sm text-muted">No link is available for this item.</p>}
      <p className="text-[12px] text-muted">The source opens in a new tab. Use <strong>Back</strong> above to return to where you were.</p>
    </div>
  )
}

/* ----------------------------------------------------------------- Help level (Scenario 5) */
const LEVELS: { id: HelpLevel; title: string; desc: string; preview: string }[] = [
  { id: 'brief', title: 'Brief', desc: 'Your goal and where you stopped.', preview: 'Goal + last position' },
  { id: 'balanced', title: 'Balanced', desc: 'Adds your main unfinished thought, your sources, and one suggested next step.', preview: 'Goal + position + thought + sources + one next step' },
  { id: 'detailed', title: 'Detailed', desc: 'Adds all thoughts, evidence, references, missing information, and a short plan around the one next step.', preview: 'Everything saved, with one recommended step' },
]

export function HelpPanel({ projectId }: { projectId: number }) {
  const { me, refreshMe, toast } = useApp()
  const qc = useQueryClient()
  const panels = usePanels()
  const resume = useResume(projectId)
  const [choice, setChoice] = usePanelState<HelpLevel | 'auto'>('choice', me?.preferences.help_level ?? 'auto')
  const [saving, setSaving] = usePanelState('saving', false)
  const suggested = resume.data?.time.suggested_help_level
  const apply = async () => {
    setSaving(true)
    await patch('/api/me/preferences', choice === 'auto' ? { clear_help_level: true } : { help_level: choice })
    await refreshMe(); await qc.invalidateQueries({ queryKey: ['resume'] })
    toast('Help level updated.'); setSaving(false); panels.back()
  }
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted">Every level shows at most one recommended next step.</p>
      <div role="radiogroup" aria-label="Help level" className="space-y-2">
        {LEVELS.map(l => (
          <label key={l.id} className={cx('flex cursor-pointer items-start gap-3 rounded-lg border p-3.5', choice === l.id ? 'border-fact bg-fact-bg ring-1 ring-fact' : 'border-line')}>
            <input type="radio" name="level" className="mt-1 accent-[rgb(var(--navy))]" checked={choice === l.id} onChange={() => setChoice(l.id)} />
            <span><span className="block font-semibold">{l.title}{suggested === l.id && <span className="ml-2 text-[12px] font-normal text-muted">suggested for your time away</span>}</span>
              <span className="text-[13px] text-muted">{l.desc}</span></span>
          </label>
        ))}
        <label className={cx('flex cursor-pointer items-start gap-3 rounded-lg border p-3.5', choice === 'auto' ? 'border-fact bg-fact-bg ring-1 ring-fact' : 'border-line')}>
          <input type="radio" name="level" className="mt-1 accent-[rgb(var(--navy))]" checked={choice === 'auto'} onChange={() => setChoice('auto')} />
          <span><span className="block font-semibold">Follow my time away</span><span className="text-[13px] text-muted">Re-Focus AI suggests a level based on how long you were away.</span></span>
        </label>
      </div>
      <div className="rounded-lg bg-canvas p-3 text-[13px]"><strong>Preview:</strong> {choice === 'auto' ? `Currently ${suggested ?? '…'}` : LEVELS.find(l => l.id === choice)!.preview}</div>
      <div className="flex justify-end gap-2"><Button onClick={panels.back}>Cancel</Button><Button variant="primary" onClick={apply} loading={saving}>Apply</Button></div>
    </div>
  )
}

/* ----------------------------------------------------------------- Accept / Partly / Reject (Scenario 6) */
export function ReviewPanel({ suggestionId, verdict: initial }: { suggestionId: number; verdict?: 'accept' | 'partly' | 'reject' }) {
  const qc = useQueryClient()
  const { toast } = useApp()
  const panels = usePanels()
  const q = useQuery({ queryKey: ['suggestion', suggestionId], queryFn: () => get<Suggestion>(`/api/suggestions/${suggestionId}`) })
  const [verdict, setVerdict] = usePanelState<'accept' | 'partly' | 'reject'>('verdict', initial ?? 'partly')
  const [text, setText] = usePanelState('text', '')
  const [task, setTask] = usePanelState('task', true)
  const [saving, setSaving] = usePanelState('saving', false)
  if (!q.data) return <Spinner />
  const s = q.data
  const submit = async () => {
    setSaving(true)
    try {
      await post(`/api/suggestions/${s.id}/feedback`, { verdict, correction: text, make_task: task && s.kind === 'next_step' })
      await qc.invalidateQueries()
      toast(verdict === 'accept' ? 'Suggestion accepted.' : text ? 'Your own step is saved and marked User Confirmed.' : 'Suggestion rejected.')
      panels.back()
    } catch (e: any) { toast(e.message, 'error'); setSaving(false) }
  }
  return (
    <div className="space-y-4">
      <ProvBox kind={s.status === 'pending' ? s.provenance : 'ai_suggestion'} title={s.kind === 'next_step' ? 'AI suggestion' : 'AI guess'}>
        <span className={cx(verdict === 'reject' && 'line-through text-muted')}>{s.ai_text ?? s.display_text}</span>
      </ProvBox>
      <div role="radiogroup" aria-label="Is the suggestion right?" className="grid grid-cols-3 gap-2">
        {(['accept', 'partly', 'reject'] as const).map(v => (
          <Button key={v} variant={verdict === v ? 'selected' : 'secondary'} role="radio" aria-checked={verdict === v} onClick={() => setVerdict(v)}>
            {v === 'accept' ? 'Accept' : v === 'partly' ? 'Partly' : 'Reject'}
          </Button>
        ))}
      </div>
      {verdict !== 'accept' && (
        <div>
          <Label htmlFor="rv-text" hint={verdict === 'reject' ? '(optional)' : undefined}>{verdict === 'partly' ? 'What is needed instead?' : 'What do you want to do instead?'}</Label>
          <TextArea id="rv-text" rows={3} value={text} onChange={e => setText(e.target.value)} placeholder="Write your own next step" />
          <p className="mt-1 text-[12px] text-muted">Your words are saved as a <strong>User Confirmed</strong> step. The AI's text is kept only as history and never shown as information.</p>
        </div>
      )}
      {s.kind === 'next_step' && (verdict === 'accept' || text) && (
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-[rgb(var(--navy))]" checked={task} onChange={e => setTask(e.target.checked)} /> Add to my tasks</label>
      )}
      <div className="flex justify-end gap-2">
        <Button onClick={panels.back}>Cancel</Button>
        <Button variant="primary" loading={saving} disabled={verdict === 'partly' && !text.trim()} onClick={submit}>
          {verdict === 'accept' ? 'Accept' : text.trim() ? 'Use my step' : 'Reject suggestion'}
        </Button>
      </div>
    </div>
  )
}

export type { Checkpoint }
