/** Feature 20 — Notes, References and Smart Bookmarks. User explanations are kept apart from AI relevance. */
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, Pin, PinOff, Plus, Search, Trash2 } from 'lucide-react'
import { del, get, patch, post } from '../api/client'
import type { Checkpoint, Note, Reference, Thought } from '../api/types'
import { Button, Card, Empty, Input, Label, PageHeader, ProvBadge, Spinner, TextArea, shortUrl, timeAgo } from '../components/ui'
import { useApp } from '../state/app'

export function NotesPage() {
  const { project } = useApp()
  const [tab, setTab] = useState<'notes' | 'refs'>('refs')
  if (!project) return <Empty title="No project selected" />
  return (
    <div>
      <PageHeader title="Notes & References" sub="Your research sources and notes, with your own reasons for saving them."
        actions={<div className="flex gap-1" role="tablist">
          <Button size="sm" role="tab" aria-selected={tab === 'refs'} variant={tab === 'refs' ? 'selected' : 'secondary'} onClick={() => setTab('refs')}>References</Button>
          <Button size="sm" role="tab" aria-selected={tab === 'notes'} variant={tab === 'notes' ? 'selected' : 'secondary'} onClick={() => setTab('notes')}>Notes</Button>
        </div>} />
      {tab === 'refs' ? <References projectId={project.id} /> : <Notes projectId={project.id} />}
    </div>
  )
}

async function togglePin(type: string, id: number, pinned: boolean, projectId: number) {
  if (pinned) await del(`/api/pins/${type}/${id}`); else await post('/api/pins', { item_type: type, item_id: id, project_id: projectId })
}

function References({ projectId }: { projectId: number }) {
  const qc = useQueryClient()
  const { toast } = useApp()
  const [q, setQ] = useState('')
  const [editing, setEditing] = useState<Reference | 'new' | null>(null)
  const list = useQuery({ queryKey: ['references', projectId, q], queryFn: () => get<{ references: Reference[] }>(`/api/references?project_id=${projectId}&q=${encodeURIComponent(q)}`) })
  return (
    <>
      <div className="mb-4 flex gap-2">
        <div className="relative flex-1"><Search className="absolute left-3 top-3 h-4 w-4 text-muted" /><Input aria-label="Search references" className="pl-9" placeholder="Search title, author, why you saved it" value={q} onChange={e => setQ(e.target.value)} /></div>
        <Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setEditing('new')}>Add reference</Button>
      </div>
      {editing && <RefForm projectId={projectId} r={editing === 'new' ? null : editing} onDone={() => { setEditing(null); qc.invalidateQueries() }} />}
      {!list.data ? <Spinner /> : list.data.references.length === 0 ? <Empty title="No references yet">Save sources here or with “Save source” in the browser extension.</Empty> : (
        <div className="grid gap-3">
          {list.data.references.map(r => (
            <Card key={r.id} className="p-4">
              <div className="flex flex-wrap items-start gap-2">
                <div className="min-w-0 flex-1">
                  <div className="font-semibold">{r.title}</div>
                  <div className="text-[13px] text-muted">{[r.authors, r.year].filter(Boolean).join(' · ')}{r.url && <> · <a className="text-fact underline" href={r.url} target="_blank" rel="noopener noreferrer">{shortUrl(r.url)} <ExternalLink className="inline h-3 w-3" /></a></>}</div>
                </div>
                <Button size="sm" variant="ghost" onClick={async () => { await togglePin('reference', r.id, r.pinned, projectId); qc.invalidateQueries() }} aria-label={r.pinned ? 'Unpin' : 'Pin'}>{r.pinned ? <PinOff className="h-4 w-4" /> : <Pin className="h-4 w-4" />}</Button>
                <Button size="sm" variant="ghost" onClick={() => setEditing(r)}>Edit</Button>
                <Button size="sm" variant="ghost" onClick={async () => { if (confirm('Delete this reference?')) { await del(`/api/references/${r.id}`); qc.invalidateQueries(); toast('Reference deleted.') } }} aria-label="Delete"><Trash2 className="h-4 w-4 text-danger" /></Button>
              </div>
              {r.why_saved && <div className="mt-3 rounded-md border border-fact/30 bg-fact-bg/50 p-2.5 text-[13px]"><div className="mb-1"><ProvBadge kind="saved_by_you" extra="Why I saved this" /></div>{r.why_saved}</div>}
              {r.ai_relevance && <div className="mt-2 rounded-md border border-dashed border-guess/50 bg-guess-bg/50 p-2.5 text-[13px]"><div className="mb-1"><ProvBadge kind="ai_guess" extra="AI-inferred relevance" /></div>{r.ai_relevance}</div>}
              {(r.thought_ids.length > 0 || r.checkpoint_ids.length > 0) && <div className="mt-2 text-[12px] text-muted">Linked to {r.thought_ids.length} thought(s) and {r.checkpoint_ids.length} checkpoint(s)</div>}
            </Card>
          ))}
        </div>
      )}
    </>
  )
}

function RefForm({ projectId, r, onDone }: { projectId: number; r: Reference | null; onDone: () => void }) {
  const [f, setF] = useState({ title: r?.title ?? '', url: r?.url ?? '', authors: r?.authors ?? '', year: r?.year?.toString() ?? '', why_saved: r?.why_saved ?? '' })
  const [thoughtIds, setThoughtIds] = useState<number[]>(r?.thought_ids ?? [])
  const [cpIds, setCpIds] = useState<number[]>(r?.checkpoint_ids ?? [])
  const thoughts = useQuery({ queryKey: ['thoughts', projectId, 'all'], queryFn: () => get<{ thoughts: Thought[] }>(`/api/thoughts?project_id=${projectId}`) })
  const cps = useQuery({ queryKey: ['checkpoints', projectId], queryFn: () => get<{ checkpoints: Checkpoint[] }>(`/api/projects/${projectId}/checkpoints`) })
  const { toast } = useApp()
  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    const body = { ...f, url: f.url || null, year: f.year ? Number(f.year) : null, thought_ids: thoughtIds, checkpoint_ids: cpIds }
    try { r ? await patch(`/api/references/${r.id}`, body) : await post('/api/references', { project_id: projectId, ...body }); toast('Reference saved.'); onDone() }
    catch (x: any) { toast(x.message, 'error') }
  }
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value })
  return (
    <Card className="mb-4 p-4">
      <form onSubmit={save} className="grid gap-3 md:grid-cols-2">
        <div className="md:col-span-2"><Label htmlFor="r-t">Article title</Label><Input id="r-t" value={f.title} onChange={set('title')} required /></div>
        <div><Label htmlFor="r-u">Source URL</Label><Input id="r-u" type="url" value={f.url} onChange={set('url')} /></div>
        <div className="grid grid-cols-[1fr_100px] gap-2"><div><Label htmlFor="r-a">Authors</Label><Input id="r-a" value={f.authors} onChange={set('authors')} /></div>
          <div><Label htmlFor="r-y">Year</Label><Input id="r-y" inputMode="numeric" value={f.year} onChange={set('year')} /></div></div>
        <div className="md:col-span-2"><Label htmlFor="r-w">Why I saved this</Label><TextArea id="r-w" rows={2} value={f.why_saved} onChange={set('why_saved')} placeholder="In your own words — kept separate from anything the AI infers" /></div>
        {!!thoughts.data?.thoughts.length && <fieldset><legend className="mb-1 text-[13px] font-semibold">Link to unfinished thoughts</legend>
          {thoughts.data.thoughts.slice(0, 8).map(t => <label key={t.id} className="flex gap-2 text-[13px]"><input type="checkbox" className="accent-[rgb(var(--navy))]" checked={thoughtIds.includes(t.id)} onChange={e => setThoughtIds(e.target.checked ? [...thoughtIds, t.id] : thoughtIds.filter(x => x !== t.id))} /><span className="truncate">{t.thinking || t.next_plan}</span></label>)}</fieldset>}
        {!!cps.data?.checkpoints.length && <fieldset><legend className="mb-1 text-[13px] font-semibold">Link to checkpoints</legend>
          {cps.data.checkpoints.slice(-8).map(c => <label key={c.id} className="flex gap-2 text-[13px]"><input type="checkbox" className="accent-[rgb(var(--navy))]" checked={cpIds.includes(c.id)} onChange={e => setCpIds(e.target.checked ? [...cpIds, c.id] : cpIds.filter(x => x !== c.id))} />{c.label}</label>)}</fieldset>}
        <div className="flex justify-end gap-2 md:col-span-2"><Button type="button" onClick={onDone}>Cancel</Button><Button type="submit" variant="primary">Save reference</Button></div>
      </form>
    </Card>
  )
}

function Notes({ projectId }: { projectId: number }) {
  const qc = useQueryClient()
  const [q, setQ] = useState('')
  const [draft, setDraft] = useState({ title: '', body: '' })
  const [edit, setEdit] = useState<Note | null>(null)
  const list = useQuery({ queryKey: ['notes', projectId, q], queryFn: () => get<{ notes: Note[] }>(`/api/notes?project_id=${projectId}&q=${encodeURIComponent(q)}`) })
  const add = async () => { await post('/api/notes', { project_id: projectId, ...draft }); setDraft({ title: '', body: '' }); qc.invalidateQueries() }
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
      <div>
        <div className="relative mb-3"><Search className="absolute left-3 top-3 h-4 w-4 text-muted" /><Input aria-label="Search notes" className="pl-9" placeholder="Search notes" value={q} onChange={e => setQ(e.target.value)} /></div>
        {!list.data ? <Spinner /> : list.data.notes.length === 0 ? <Empty title="No notes yet" /> : (
          <div className="grid gap-3">
            {list.data.notes.map(n => edit?.id === n.id ? (
              <Card key={n.id} className="space-y-2 p-4">
                <Input aria-label="Title" value={edit.title} onChange={e => setEdit({ ...edit, title: e.target.value })} />
                <TextArea aria-label="Note" rows={4} value={edit.body} onChange={e => setEdit({ ...edit, body: e.target.value })} />
                <div className="flex justify-end gap-2"><Button size="sm" onClick={() => setEdit(null)}>Cancel</Button><Button size="sm" variant="primary" onClick={async () => { await patch(`/api/notes/${n.id}`, { title: edit.title, body: edit.body }); setEdit(null); qc.invalidateQueries() }}>Save</Button></div>
              </Card>
            ) : (
              <Card key={n.id} className="p-4">
                <div className="flex items-start gap-2">
                  <div className="min-w-0 flex-1"><div className="font-semibold">{n.title || 'Untitled note'}</div><div className="text-[12px] text-muted">{timeAgo(n.updated_at)}</div></div>
                  <Button size="sm" variant="ghost" onClick={async () => { await togglePin('note', n.id, n.pinned, projectId); qc.invalidateQueries() }} aria-label={n.pinned ? 'Unpin' : 'Pin'}>{n.pinned ? <PinOff className="h-4 w-4" /> : <Pin className="h-4 w-4" />}</Button>
                  <Button size="sm" variant="ghost" onClick={() => setEdit(n)}>Edit</Button>
                  <Button size="sm" variant="ghost" onClick={async () => { if (confirm('Delete this note?')) { await del(`/api/notes/${n.id}`); qc.invalidateQueries() } }} aria-label="Delete"><Trash2 className="h-4 w-4 text-danger" /></Button>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-sm">{n.body}</p>
              </Card>
            ))}
          </div>
        )}
      </div>
      <Card className="h-fit space-y-2 p-4">
        <div className="font-semibold">New note</div>
        <Label htmlFor="n-t">Title</Label><Input id="n-t" value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} />
        <Label htmlFor="n-b">Note</Label><TextArea id="n-b" rows={5} value={draft.body} onChange={e => setDraft({ ...draft, body: e.target.value })} />
        <Button variant="primary" disabled={!draft.body.trim() && !draft.title.trim()} onClick={add}>Save note</Button>
      </Card>
    </div>
  )
}
