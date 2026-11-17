import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, ChevronRight, Copy, GitCompare, Play, RotateCcw, Trash2 } from 'lucide-react'
import { diffWordsWithSpace } from 'diff'
import { ApiError, del, get, post } from '../api/client'
import type { Checkpoint } from '../api/types'
import { Button, ProvBox, Spinner, fmtTime } from '../components/ui'
import { useApp } from '../state/app'
import { usePanelState, usePanels } from '../state/panels'
import { resumeWriting } from '../components/ResumeCardView'

/* ----------------------------------------------------------------- Checkpoint detail (5B) */
export function CheckpointPanel({ checkpointId }: { checkpointId: number }) {
  const [id, setId] = usePanelState('id', checkpointId)
  const q = useQuery({ queryKey: ['checkpoint', id], queryFn: () => get<Checkpoint>(`/api/checkpoints/${id}`) })
  const panels = usePanels()
  const qc = useQueryClient()
  const nav = useNavigate()
  const { toast } = useApp()
  if (!q.data) return <Spinner />
  const c = q.data

  const restore = async () => {
    try {
      await post(`/api/checkpoints/${c.id}/restore`)
      await qc.invalidateQueries()
      toast('Restored. Your newer text was saved as a version first.', 'ok', { label: 'Open document', run: () => nav(`/documents/${c.document_id}`) })
    } catch (e) {
      const err = e as ApiError
      if (err.status === 409 && err.detail?.copy_text !== undefined) {
        await navigator.clipboard?.writeText(err.detail.copy_text).catch(() => {})
        toast('Re-Focus AI never writes into Google Docs or Word. The older text was copied to your clipboard.', 'info')
      } else toast(err.message, 'error')
    }
  }
  const remove = async () => {
    if (!confirm('Delete this checkpoint? Its saved position, question and source list are removed. Your document and notes are kept.')) return
    await del(`/api/checkpoints/${c.id}`); await qc.invalidateQueries(); toast('Checkpoint deleted.'); panels.close()
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Button size="sm" variant="ghost" disabled={!c.older_id} onClick={() => c.older_id && setId(c.older_id)} icon={<ChevronLeft className="h-4 w-4" />}>Older checkpoint</Button>
        <span className="text-[13px] text-muted">Checkpoint {c.index} of {c.total}</span>
        <Button size="sm" variant="ghost" disabled={!c.newer_id} onClick={() => c.newer_id && setId(c.newer_id)}>Newer checkpoint<ChevronRight className="h-4 w-4" /></Button>
      </div>
      <div><div className="font-semibold">{c.label}</div><div className="text-[13px] text-muted">{fmtTime(c.created_at)}{c.resumed_at && ` · resumed ${fmtTime(c.resumed_at)}`}</div></div>
      {c.goal && <ProvBox kind="saved_by_you" title="Goal">{c.goal}</ProvBox>}
      {c.position && <ProvBox kind={c.position.provenance ?? 'saved_by_you'} title="Where you stopped"><span className="font-serif italic">“…{c.position.paragraph_text.slice(-200)}”</span></ProvBox>}
      {c.thoughts?.map(t => <ProvBox key={t.id} kind="saved_by_you" title="Unfinished thought">{t.thinking}{t.missing && <p className="mt-1 text-muted">Missing: {t.missing}</p>}</ProvBox>)}
      {c.future_self && !c.future_self.skipped && <ProvBox kind="saved_by_you" title={c.future_self.question}>{c.future_self.answer || <span className="text-muted">No answer</span>}</ProvBox>}
      {!!c.sources?.length && (
        <div><div className="mb-1 text-[13px] font-semibold">Sources kept ({c.sources.length})</div>
          <ul className="space-y-1 text-[13px]">{c.sources.map((s, i) => <li key={i} className="truncate">• {s.title || s.url} <span className="text-muted">({s.provenance_label})</span></li>)}</ul></div>
      )}
      <div className="flex flex-wrap gap-2 border-t border-line pt-3">
        <Button variant="primary" icon={<Play className="h-4 w-4" />} onClick={async () => { await resumeWriting(c.id, nav); panels.close() }}>Resume here</Button>
        <Button onClick={() => panels.open('resume', { projectId: c.project_id, checkpointId: c.id })}>Open resume card</Button>
        {c.document_id && <Button icon={<GitCompare className="h-4 w-4" />} onClick={() => panels.open('compare', { documentId: c.document_id, a: c.document_version_id ? `v${c.document_version_id}` : `cp${c.id}`, b: 'current' })}>Compare with now</Button>}
        {c.document_id && <Button icon={<RotateCcw className="h-4 w-4" />} onClick={restore}>Restore this version</Button>}
        <Button variant="danger" icon={<Trash2 className="h-4 w-4" />} onClick={remove}>Delete</Button>
      </div>
      <p className="text-[12px] text-muted">Viewing older checkpoints never deletes newer ones. Restore saves your current text as a new version first.</p>
    </div>
  )
}

/* ----------------------------------------------------------------- Before / after comparison (19) */
interface VersionList { versions: { key: string; label: string; created_at: string; reason: string }[]; read_only: boolean }

export function ComparePanel({ documentId, a: a0, b: b0 }: { documentId: number; a?: string; b?: string }) {
  const list = useQuery({ queryKey: ['versions', documentId], queryFn: () => get<VersionList>(`/api/documents/${documentId}/versions`) })
  const [a, setA] = usePanelState('a', a0 ?? '')
  const [b, setB] = usePanelState('b', b0 ?? 'current')
  const cmp = useQuery({ queryKey: ['compare', documentId, a, b], enabled: !!a && !!b,
    queryFn: () => get<{ a_text: string; b_text: string; a_label: string; b_label: string; read_only: boolean }>(`/api/documents/${documentId}/compare?a=${a}&b=${b}`) })
  const qc = useQueryClient()
  const { toast } = useApp()
  if (!list.data) return <Spinner />
  const vs = list.data.versions
  const parts = cmp.data ? diffWordsWithSpace(cmp.data.a_text, cmp.data.b_text) : []
  const added = parts.filter(p => p.added).reduce((n, p) => n + p.value.split(/\s+/).filter(Boolean).length, 0)
  const removed = parts.filter(p => p.removed).reduce((n, p) => n + p.value.split(/\s+/).filter(Boolean).length, 0)

  const restore = async () => {
    if (!a.startsWith('v')) return
    await post(`/api/documents/${documentId}/versions/${a.slice(1)}/restore`)
    await qc.invalidateQueries(); toast('Older version restored. The current text was saved as a version first.')
  }
  const sel = (v: string, set: (x: string) => void, id: string, label: string) => (
    <div className="flex-1"><label htmlFor={id} className="mb-1 block text-[12px] font-semibold text-muted">{label}</label>
      <select id={id} value={v} onChange={e => set(e.target.value)} className="h-9 w-full rounded-md border border-line bg-surface px-2 text-[13px]">
        <option value="">Choose…</option><option value="current">Current text</option>
        {vs.map(x => <option key={x.key} value={x.key}>{x.label} · {fmtTime(x.created_at)}</option>)}
      </select></div>
  )
  return (
    <div className="space-y-4">
      <div className="flex gap-2">{sel(a, setA, 'cmp-a', 'Before')}{sel(b, setB, 'cmp-b', 'After')}</div>
      {cmp.data && (
        <>
          <div className="flex gap-3 text-[13px]"><span className="diff-add rounded px-1.5">+{added} words added</span><span className="diff-del rounded px-1.5">−{removed} words removed</span></div>
          <div className="max-h-[55vh] overflow-y-auto whitespace-pre-wrap rounded-lg border border-line p-3 font-serif text-[14px] leading-relaxed">
            {parts.map((p, i) => p.added ? <ins key={i} className="diff-add" aria-label="added">{p.value}</ins>
              : p.removed ? <del key={i} className="diff-del" aria-label="removed">{p.value}</del> : <span key={i}>{p.value}</span>)}
          </div>
          {list.data.read_only
            ? <Button icon={<Copy className="h-4 w-4" />} onClick={() => { navigator.clipboard?.writeText(cmp.data!.a_text); toast('Older text copied. Re-Focus AI never writes into Google Docs or Word.') }}>Copy older text</Button>
            : a.startsWith('v') && <Button icon={<RotateCcw className="h-4 w-4" />} onClick={restore}>Restore “Before” version</Button>}
        </>
      )}
    </div>
  )
}
