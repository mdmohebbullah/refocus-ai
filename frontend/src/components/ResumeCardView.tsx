/**
 * Scenario 3 — the Resume Card. Facts (solid boxes) are always kept apart from AI guesses
 * (dashed boxes). The amount shown follows the help level (Feature 12).
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, ChevronLeft, ChevronRight, CircleHelp, ExternalLink, History, Library, Pin, Play, SlidersHorizontal } from 'lucide-react'
import { get, post } from '../api/client'
import type { HelpLevel, ResumeCard, Suggestion } from '../api/types'
import { Button, Pill, ProvBox, Spinner, fmtMinutes, fmtTime } from './ui'
import { usePanels } from '../state/panels'
import { useApp } from '../state/app'
import { useShortcutEvent } from '../hooks/useShortcuts'

export function useResume(projectId: number | undefined, checkpointId?: number | null) {
  return useQuery({
    queryKey: ['resume', projectId, checkpointId ?? null],
    queryFn: () => get<ResumeCard>(`/api/projects/${projectId}/resume${checkpointId ? `?checkpoint_id=${checkpointId}` : ''}`),
    enabled: !!projectId,
  })
}

export async function resumeWriting(checkpointId: number, nav: (to: string) => void) {
  const r = await post(`/api/checkpoints/${checkpointId}/resume-writing`)
  if (r.mode === 'editor') {
    const q = new URLSearchParams({ cursor: String(r.cursor ?? ''), highlight: r.highlight_text ?? '' })
    nav(`/documents/${r.document_id}?${q}`)
  } else if (r.mode === 'external') {
    return r
  }
  return null
}

function SuggestionBlock({ s, title }: { s: Suggestion; title: string }) {
  const panels = usePanels()
  const qc = useQueryClient()
  const { toast } = useApp()
  const accept = async () => {
    await post(`/api/suggestions/${s.id}/feedback`, { verdict: 'accept' })
    qc.invalidateQueries({ queryKey: ['resume'] })
    toast('Marked as correct.')
  }
  if (s.status === 'rejected' && !s.user_text) {
    return <ProvBox kind="ai_guess" title={title}><span className="text-muted">You rejected this guess. It is not used as information.</span></ProvBox>
  }
  return (
    <ProvBox kind={s.provenance} title={title}
      right={s.provenance !== 'user_confirmed' && <span className="text-[11px] text-muted">{s.provider_label}</span>}>
      <p>{s.display_text}</p>
      {s.user_text && s.ai_text && <p className="mt-1 text-[12px] text-muted line-through" aria-label="Original AI suggestion">{s.ai_text}</p>}
      {s.context_incomplete && <p className="mt-1 text-[12px] text-guess">Context is incomplete, so treat this as a rough guess.</p>}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button size="sm" icon={<CircleHelp className="h-3.5 w-3.5" />} onClick={() => panels.open('why', { suggestionId: s.id })}>Why?</Button>
        {s.status === 'pending' && <>
          <Button size="sm" onClick={accept}>Accept</Button>
          <Button size="sm" onClick={() => panels.open('review', { suggestionId: s.id, verdict: 'partly' })}>Partly</Button>
          <Button size="sm" onClick={() => panels.open('review', { suggestionId: s.id, verdict: 'reject' })}>Reject</Button>
        </>}
        {s.status !== 'pending' && <Button size="sm" variant="ghost" onClick={() => panels.open('review', { suggestionId: s.id, verdict: s.status === 'accepted' ? 'accept' : s.status === 'rejected' ? 'reject' : 'partly' })}>Change answer</Button>}
      </div>
    </ProvBox>
  )
}

const LEVEL_LABEL: Record<HelpLevel, string> = { brief: 'Brief', balanced: 'Balanced', detailed: 'Detailed' }

export function ResumeCardView({ projectId, checkpointId, onNavigateCheckpoint, compact }: {
  projectId: number; checkpointId?: number | null; onNavigateCheckpoint: (id: number) => void; compact?: boolean
}) {
  const q = useResume(projectId, checkpointId)
  const panels = usePanels()
  const nav = useNavigate()
  const { toast } = useApp()
  useShortcutEvent('older_checkpoint', () => { const id = q.data?.timeline.older_id; if (id) onNavigateCheckpoint(id) })
  useShortcutEvent('newer_checkpoint', () => { const id = q.data?.timeline.newer_id; if (id) onNavigateCheckpoint(id) })
  if (q.isLoading) return <Spinner label="Reading your saved context" />
  if (q.error || !q.data) return <p className="text-sm text-danger">Couldn't load the resume card: {(q.error as Error)?.message}</p>
  const c = q.data
  const level = c.time.help_level
  const detailed = level === 'detailed', balanced = level !== 'brief'
  const f = c.facts

  const onResume = async () => {
    if (!c.checkpoint) { if (c.document) nav(`/documents/${c.document.id}`); return }
    const ext = await resumeWriting(c.checkpoint.id, nav)
    if (ext) {
      panels.open('source', { title: `Continue in ${ext.source === 'google_docs' ? 'Google Docs' : 'Word'}`, url: ext.open_url,
        excerpt: ext.show_paragraph, note: ext.instruction, kind: 'Where you stopped' })
      if (ext.open_url) window.open(ext.open_url, '_blank', 'noopener')
    }
    toast('Welcome back. Your place is restored.')
  }

  return (
    <div className="space-y-4">
      {/* Feature 5B — checkpoint timeline */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          <Button size="sm" variant="ghost" disabled={!c.timeline.older_id} onClick={() => c.timeline.older_id && onNavigateCheckpoint(c.timeline.older_id)}
            icon={<ChevronLeft className="h-4 w-4" />} aria-label="Older checkpoint" title="Older checkpoint (Alt+Shift+[)">Older checkpoint</Button>
          <span className="px-2 text-[13px] text-muted">{c.timeline.total ? `Checkpoint ${c.timeline.index} of ${c.timeline.total}` : 'No checkpoints yet'}</span>
          <Button size="sm" variant="ghost" disabled={!c.timeline.newer_id} onClick={() => c.timeline.newer_id && onNavigateCheckpoint(c.timeline.newer_id)}
            aria-label="Newer checkpoint" title="Newer checkpoint (Alt+Shift+])">Newer checkpoint<ChevronRight className="h-4 w-4" /></Button>
        </div>
        {c.checkpoint && <span className="text-[12px] text-muted">Saved {fmtTime(c.checkpoint.created_at)}</span>}
      </div>

      <div className="flex flex-wrap items-center gap-2 rounded-lg bg-canvas px-3 py-2 text-[13px]">
        <span><strong>Time away:</strong> {c.time.active_now ? 'You are active now' : fmtMinutes(c.time.minutes_away)}</span>
        <span className="text-muted">·</span>
        <span>Help level: <strong>{LEVEL_LABEL[level]}</strong> <span className="text-muted">({c.time.help_level_source === 'user_preference' ? 'your choice' : 'suggested for your time away'})</span></span>
        <Button size="sm" variant="ghost" className="ml-auto" icon={<SlidersHorizontal className="h-3.5 w-3.5" />} onClick={() => panels.open('help', { projectId })}>Change help level</Button>
      </div>

      {c.context_incomplete && c.incomplete_reasons.length > 0 && (
        <div className="flex gap-2 rounded-lg border border-guess/40 bg-guess-bg/50 px-3 py-2 text-[13px]">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-guess" aria-hidden />
          <div><strong>Context is incomplete.</strong> {c.incomplete_reasons.join(' ')}</div>
        </div>
      )}

      {/* 1. What was I trying to do? */}
      <ProvBox kind="saved_by_you" title="What you were trying to do">
        {f.goal ? f.goal.text : <span className="text-muted">No goal saved.</span>}
      </ProvBox>

      {/* 2. Where did I stop? */}
      {f.position ? (
        <ProvBox kind={f.position.provenance ?? 'saved_by_you'} title="Where you stopped"
          right={c.document && <span className="text-[12px] text-muted">{c.document.title}{c.document.read_only ? ` · ${c.document.source === 'google_docs' ? 'Google Docs' : 'Word'}` : ''}</span>}>
          <p className="font-serif italic">“…{f.position.paragraph_text.slice(-220) || 'start of document'}”</p>
          {f.position.source === 'ai_guess' && <p className="mt-1 text-[12px] text-guess">You didn't mark a paragraph, so this position is a guess from the change since your last snapshot.</p>}
        </ProvBox>
      ) : <ProvBox kind="saved_by_you" title="Where you stopped"><span className="text-muted">No writing position was saved.</span></ProvBox>}

      {balanced && f.thoughts[0] && (
        <ProvBox kind="saved_by_you" title="Your unfinished thought">
          {f.thoughts[0].thinking && <p>{f.thoughts[0].thinking}</p>}
          {f.thoughts[0].missing && <p className="mt-1"><span className="text-muted">Missing:</span> {f.thoughts[0].missing}</p>}
          {f.thoughts[0].next_plan && <p className="mt-1"><span className="text-muted">You planned:</span> {f.thoughts[0].next_plan}</p>}
        </ProvBox>
      )}

      {balanced && f.future_self && !f.future_self.skipped && f.future_self.answer && (
        <ProvBox kind="saved_by_you" title="Your answer to your future self">
          <p className="text-[13px] text-muted">{f.future_self.question}</p>
          <p className="mt-1">{f.future_self.answer}</p>
        </ProvBox>
      )}

      {balanced && <SuggestionBlock s={c.ai.context_guess} title="What you may have been doing" />}

      {balanced && f.sources.length > 0 && (
        <div>
          <div className="mb-2 text-[13px] font-semibold">Sources you kept</div>
          <ul className="space-y-1.5">
            {f.sources.slice(0, detailed ? 20 : 3).map((s, i) => (
              <li key={i} className="flex items-center gap-2 rounded-md border border-line px-3 py-2 text-[13px]">
                <span className="min-w-0 flex-1 truncate">{s.title || s.url}</span>
                <Pill tone={s.provenance === 'saved_by_you' ? 'blue' : 'gray'}>{s.provenance_label}</Pill>
                {s.url && <button className="text-fact" onClick={() => panels.open('source', { title: s.title, url: s.url, kind: s.provenance_label })} aria-label={`Preview ${s.title}`}><ExternalLink className="h-4 w-4" /></button>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 3. What should I do now? — one step at most */}
      {balanced && <SuggestionBlock s={c.ai.next_step} title="Suggested next step" />}

      {detailed && (
        <div className="space-y-3">
          {f.thoughts.slice(1).map(t => (
            <ProvBox key={t.id} kind="saved_by_you" title="Another unfinished thought">{t.thinking || t.next_plan}{t.missing && <p className="mt-1"><span className="text-muted">Missing:</span> {t.missing}</p>}</ProvBox>
          ))}
          {c.tasks.length > 0 && (
            <details className="rounded-lg border border-line p-3">
              <summary className="cursor-pointer text-[13px] font-semibold">More options · open tasks ({c.tasks.length})</summary>
              <ul className="mt-2 space-y-1 text-[13px]">{c.tasks.map(t => <li key={t.id}>• {t.title} <span className="text-muted">({t.provenance_label})</span></li>)}</ul>
            </details>
          )}
        </div>
      )}

      {c.pinned.length > 0 && !compact && (
        <div className="rounded-lg border border-line p-3">
          <div className="mb-1 flex items-center gap-1.5 text-[13px] font-semibold"><Pin className="h-3.5 w-3.5" />Pinned</div>
          <ul className="space-y-1 text-[13px]">
            {c.pinned.map(p => <li key={`${p.item_type}${p.item.id}`}>• {p.item.title || p.item.thinking || p.item.text || p.item.body}</li>)}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap gap-2 border-t border-line pt-4">
        <Button variant="primary" size="lg" icon={<Play className="h-4 w-4" />} onClick={onResume}>Resume writing</Button>
        <Button icon={<Library className="h-4 w-4" />} onClick={() => panels.open('source', { list: true, projectId, checkpointId: c.checkpoint?.id ?? null })}>Review sources</Button>
        <Button icon={<History className="h-4 w-4" />} onClick={() => nav('/history')}>Review history</Button>
      </div>
    </div>
  )
}
