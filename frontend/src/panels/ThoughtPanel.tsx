/** Scenario 2 — Record an unfinished idea (Feature 8). User wording is saved exactly. */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { CheckCircle2, ChevronLeft, ChevronRight, MapPin, Pin, PinOff, Play } from 'lucide-react'
import { del, get, patch, post } from '../api/client'
import type { Checkpoint, Reference, Thought } from '../api/types'
import { Button, Check, Label, ProvBadge, Spinner, TextArea } from '../components/ui'
import { VoiceButton } from '../components/VoiceButton'
import { editorBridge, useApp } from '../state/app'
import { usePanelState, usePanels } from '../state/panels'
import { useShortcutEvent } from '../hooks/useShortcuts'

type Detail = Thought & { previous_id: number | null; next_id: number | null; position_in_list: number; total: number }

export function ThoughtPanel({ projectId, thoughtId, checkpointId }: { projectId: number; thoughtId?: number; checkpointId?: number }) {
  const q = useQuery({ queryKey: ['thought', thoughtId], queryFn: () => get<Detail>(`/api/thoughts/${thoughtId}`), enabled: !!thoughtId })
  if (thoughtId && !q.data) return <Spinner />
  return <ThoughtForm key={thoughtId ?? 'new'} projectId={projectId} t={q.data ?? null} checkpointId={checkpointId} />
}

function ThoughtForm({ projectId, t, checkpointId }: { projectId: number; t: Detail | null; checkpointId?: number }) {
  const qc = useQueryClient()
  const panels = usePanels()
  const nav = useNavigate()
  const { toast } = useApp()
  const refs = useQuery({ queryKey: ['references', projectId], queryFn: () => get<{ references: Reference[] }>(`/api/references?project_id=${projectId}`) })
  const cps = useQuery({ queryKey: ['checkpoints', projectId], queryFn: () => get<{ checkpoints: Checkpoint[] }>(`/api/projects/${projectId}/checkpoints`) })
  const [thinking, setThinking] = usePanelState('thinking', t?.thinking ?? '')
  const [missing, setMissing] = usePanelState('missing', t?.missing ?? '')
  const [nextPlan, setNextPlan] = usePanelState('nextPlan', t?.next_plan ?? '')
  const [refIds, setRefIds] = usePanelState<number[]>('refIds', t?.reference_ids ?? [])
  const [cp, setCp] = usePanelState<number | null>('cp', t?.checkpoint_id ?? checkpointId ?? null)
  const [position, setPosition] = usePanelState<any>('position', t?.position ?? null)
  const [origin, setOrigin] = usePanelState<'typed' | 'voice'>('origin', (t?.origin as any) ?? 'typed')
  const [saving, setSaving] = usePanelState('saving', false)

  const linkPosition = () => {
    const p = editorBridge.getPosition?.()
    if (!p) { toast('Open your document first, then link the cursor position.', 'info'); return }
    setPosition({ cursor: p.cursor, paragraph_index: p.paragraph_index, paragraph_text: p.paragraph_text, source: 'cursor' })
  }

  const save = async () => {
    setSaving(true)
    const body = { thinking, missing, next_plan: nextPlan, reference_ids: refIds, checkpoint_id: cp,
      position: position ? { cursor: position.cursor, paragraph_index: position.paragraph_index, paragraph_text: position.paragraph_text, source: position.source ?? 'cursor' } : null }
    try {
      if (t) await patch(`/api/thoughts/${t.id}`, body)
      else await post('/api/thoughts', { project_id: projectId, document_id: editorBridge.docId, origin, ...body })
      await qc.invalidateQueries()
      toast('Thought saved as your own note.')
      panels.back()
      if (!panels.canBack) panels.close()
    } catch (e: any) { toast(e.message, 'error') } finally { setSaving(false) }
  }

  useShortcutEvent('save_thought', () => { if (thinking.trim() || missing.trim() || nextPlan.trim()) save() })

  const togglePin = async () => {
    if (!t) return
    if (t.pinned) await del(`/api/pins/thought/${t.id}`)
    else await post('/api/pins', { item_type: 'thought', item_id: t.id, project_id: projectId })
    qc.invalidateQueries()
  }
  const complete = async () => { if (!t) return; await patch(`/api/thoughts/${t.id}`, { completed: !t.completed }); qc.invalidateQueries(); toast(t.completed ? 'Marked as open again.' : 'Marked completed.') }
  const resumeFrom = () => {
    const p = t?.position
    if (!t?.document_id) { toast('This thought is not linked to a document position.', 'info'); return }
    nav(`/documents/${t.document_id}?` + new URLSearchParams({ cursor: String(p?.cursor ?? ''), highlight: p?.paragraph_text ?? '' }))
    panels.close()
  }

  return (
    <div className="space-y-4">
      {t && (
        <div className="flex items-center justify-between">
          <Button size="sm" variant="ghost" disabled={!t.previous_id} onClick={() => panels.open('thought', { projectId, thoughtId: t.previous_id })} icon={<ChevronLeft className="h-4 w-4" />}>Previous thought</Button>
          <span className="text-[12px] text-muted">{t.position_in_list} of {t.total}</span>
          <Button size="sm" variant="ghost" disabled={!t.next_id} onClick={() => panels.open('thought', { projectId, thoughtId: t.next_id })}>Next thought<ChevronRight className="h-4 w-4" /></Button>
        </div>
      )}
      <div className="flex items-center gap-2"><ProvBadge kind="saved_by_you" /><span className="text-[12px] text-muted">Saved exactly as you write it.</span></div>
      <div><Label htmlFor="th-1">What were you thinking?</Label>
        <div className="flex gap-2"><TextArea id="th-1" rows={3} value={thinking} onChange={e => setThinking(e.target.value)} autoFocus={!t} />
          <VoiceButton projectId={projectId} onText={x => { setThinking((thinking ? thinking + ' ' : '') + x); setOrigin('voice') }} /></div></div>
      <div><Label htmlFor="th-2">What information is missing?</Label>
        <div className="flex gap-2"><TextArea id="th-2" rows={2} value={missing} onChange={e => setMissing(e.target.value)} />
          <VoiceButton projectId={projectId} onText={x => setMissing((missing ? missing + ' ' : '') + x)} /></div></div>
      <div><Label htmlFor="th-3">What were you planning to do next?</Label>
        <div className="flex gap-2"><TextArea id="th-3" rows={2} value={nextPlan} onChange={e => setNextPlan(e.target.value)} />
          <VoiceButton projectId={projectId} onText={x => setNextPlan((nextPlan ? nextPlan + ' ' : '') + x)} /></div></div>

      <fieldset className="space-y-2 border-t border-line pt-3">
        <legend className="text-[13px] font-semibold">Links</legend>
        <div className="flex flex-wrap items-center gap-2 text-[13px]">
          <Button size="sm" icon={<MapPin className="h-3.5 w-3.5" />} onClick={linkPosition}>Link to writing position</Button>
          {position && <span className="truncate font-serif italic text-muted">“…{(position.paragraph_text || '').slice(-60)}”</span>}
        </div>
        <div>
          <Label htmlFor="th-cp">Checkpoint</Label>
          <select id="th-cp" value={cp ?? ''} onChange={e => setCp(e.target.value ? Number(e.target.value) : null)} className="h-10 w-full rounded-md border border-line bg-surface px-2 text-sm">
            <option value="">Not linked</option>
            {cps.data?.checkpoints.map(c => <option key={c.id} value={c.id}>{c.index}. {c.label}</option>)}
          </select>
        </div>
        {!!refs.data?.references.length && (
          <div><div className="mb-1 text-[13px] font-semibold">Sources</div>
            {refs.data.references.map(r => <Check key={r.id} checked={refIds.includes(r.id)} onChange={v => setRefIds(v ? [...refIds, r.id] : refIds.filter(x => x !== r.id))}>{r.title}</Check>)}
          </div>
        )}
      </fieldset>

      {t && (
        <div className="flex flex-wrap gap-2 border-t border-line pt-3">
          <Button size="sm" icon={t.pinned ? <PinOff className="h-3.5 w-3.5" /> : <Pin className="h-3.5 w-3.5" />} onClick={togglePin}>{t.pinned ? 'Unpin' : 'Pin'}</Button>
          <Button size="sm" icon={<CheckCircle2 className="h-3.5 w-3.5" />} onClick={complete}>{t.completed ? 'Reopen' : 'Mark completed'}</Button>
          <Button size="sm" icon={<Play className="h-3.5 w-3.5" />} onClick={resumeFrom}>Resume from thought</Button>
        </div>
      )}
      <div className="flex justify-end gap-2 border-t border-line pt-3">
        <Button onClick={() => (panels.canBack ? panels.back() : panels.close())}>Cancel</Button>
        <Button variant="primary" loading={saving} disabled={!(thinking.trim() || missing.trim() || nextPlan.trim())} onClick={save}>Save as my note</Button>
      </div>
    </div>
  )
}
