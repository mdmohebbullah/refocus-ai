/** Feature 2 — Project Management. */
import { useRef, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { FilePlus2, FileText, Link2, Pencil, Pin, PinOff, Search, Trash2, Upload } from 'lucide-react'
import { api, del, get, patch, post } from '../api/client'
import type { Doc, Project } from '../api/types'
import { Button, Card, Empty, Input, Label, PageHeader, Pill, Spinner, TextArea, timeAgo } from '../components/ui'
import { useApp } from '../state/app'

const CAT_LABEL: Record<string, string> = { research_paper: 'Research paper', assignment: 'Assignment', dissertation: 'Dissertation', literature_review: 'Literature review', general: 'General' }

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true" aria-label={title} onClick={onClose}>
      <div className="w-full max-w-lg rounded-xl border border-line bg-surface p-6 shadow-2xl" onClick={e => e.stopPropagation()}>
        <h2 className="mb-4 text-lg font-semibold">{title}</h2>{children}
      </div>
    </div>
  )
}

export function ProjectForm({ initial, onDone }: { initial?: Project; onDone: (p: Project) => void }) {
  const [name, setName] = useState(initial?.name ?? '')
  const [category, setCategory] = useState(initial?.category ?? 'literature_review')
  const [goal, setGoal] = useState(initial?.goal ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [busy, setBusy] = useState(false)
  const { toast } = useApp()
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true)
    try {
      const p = initial ? await patch<Project>(`/api/projects/${initial.id}`, { name, category, goal, description })
        : await post<Project>('/api/projects', { name, category, goal, description })
      onDone(p)
    } catch (x: any) { toast(x.message, 'error') } finally { setBusy(false) }
  }
  return (
    <form onSubmit={submit} className="space-y-3">
      <div><Label htmlFor="pf-name">Project name</Label><Input id="pf-name" value={name} onChange={e => setName(e.target.value)} required autoFocus /></div>
      <div><Label htmlFor="pf-cat">Type</Label>
        <select id="pf-cat" value={category} onChange={e => setCategory(e.target.value)} className="h-10 w-full rounded-md border border-line bg-surface px-2 text-sm">
          {Object.entries(CAT_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select></div>
      <div><Label htmlFor="pf-goal" hint="(optional)">Goal</Label><TextArea id="pf-goal" rows={2} value={goal} onChange={e => setGoal(e.target.value)} placeholder="What are you trying to finish?" /></div>
      <div><Label htmlFor="pf-desc" hint="(optional)">Description</Label><TextArea id="pf-desc" rows={2} value={description} onChange={e => setDescription(e.target.value)} /></div>
      <div className="flex justify-end gap-2 pt-2"><Button type="submit" variant="primary" loading={busy}>{initial ? 'Save changes' : 'Create project'}</Button></div>
    </form>
  )
}

export function NewProjectButton({ label = 'New project', ...rest }: { label?: string } & React.ComponentProps<typeof Button>) {
  const [open, setOpen] = useState(false)
  const qc = useQueryClient()
  const nav = useNavigate()
  return (
    <>
      <Button icon={<FilePlus2 className="h-4 w-4" />} {...rest} onClick={() => setOpen(true)}>{label}</Button>
      {open && <Modal title="Start a new project" onClose={() => setOpen(false)}>
        <ProjectForm onDone={async p => { setOpen(false); await qc.invalidateQueries(); nav(`/projects/${p.id}`) }} />
      </Modal>}
    </>
  )
}

export function ProjectsPage() {
  const [q, setQ] = useState('')
  const [cat, setCat] = useState('')
  const qc = useQueryClient()
  const { setProjectId, toast } = useApp()
  const list = useQuery({ queryKey: ['projects', q, cat], queryFn: () => get<{ projects: Project[] }>(`/api/projects?q=${encodeURIComponent(q)}&category=${cat}`) })
  const pin = async (p: Project) => {
    if (p.pinned) await del(`/api/pins/project/${p.id}`); else await post('/api/pins', { item_type: 'project', item_id: p.id })
    qc.invalidateQueries()
  }
  const remove = async (p: Project) => {
    if (!confirm(`Delete “${p.name}”? This permanently removes its documents, checkpoints, thoughts, notes and references.`)) return
    await del(`/api/projects/${p.id}`); await qc.invalidateQueries(); toast('Project deleted.')
  }
  return (
    <div>
      <PageHeader title="My Projects" sub="Each project keeps its own documents, checkpoints and notes." actions={<NewProjectButton variant="primary" />} />
      <div className="mb-4 flex flex-wrap gap-2">
        <div className="relative min-w-[220px] flex-1"><Search className="absolute left-3 top-3 h-4 w-4 text-muted" aria-hidden />
          <Input aria-label="Search projects" className="pl-9" placeholder="Search projects" value={q} onChange={e => setQ(e.target.value)} /></div>
        <select aria-label="Filter by type" value={cat} onChange={e => setCat(e.target.value)} className="h-10 rounded-md border border-line bg-surface px-2 text-sm">
          <option value="">All types</option>{Object.entries(CAT_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>
      {!list.data ? <Spinner /> : list.data.projects.length === 0 ? <Empty title="No projects found" action={<NewProjectButton />} /> : (
        <div className="grid gap-3 md:grid-cols-2">
          {list.data.projects.map(p => (
            <Card key={p.id} className="flex flex-col p-4">
              <div className="flex items-start gap-2">
                <Link to={`/projects/${p.id}`} onClick={() => setProjectId(p.id)} className="min-w-0 flex-1">
                  <div className="truncate font-semibold hover:text-fact">{p.name}</div>
                  <div className="mt-1 flex items-center gap-2 text-[12px] text-muted"><Pill>{CAT_LABEL[p.category] ?? p.category}</Pill>active {timeAgo(p.last_active_at ?? p.updated_at)}</div>
                </Link>
                <Button size="sm" variant="ghost" onClick={() => pin(p)} aria-label={p.pinned ? 'Unpin project' : 'Pin project'}>{p.pinned ? <PinOff className="h-4 w-4" /> : <Pin className="h-4 w-4" />}</Button>
                <Button size="sm" variant="ghost" onClick={() => remove(p)} aria-label="Delete project"><Trash2 className="h-4 w-4 text-danger" /></Button>
              </div>
              {p.goal && <p className="mt-3 line-clamp-2 text-[13px] text-muted">Goal: {p.goal}</p>}
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

export function ProjectPage() {
  const { id } = useParams()
  const pid = Number(id)
  const qc = useQueryClient()
  const nav = useNavigate()
  const { toast, setProjectId, project: current } = useApp()
  const q = useQuery({ queryKey: ['project', pid], queryFn: () => get<Project & { documents: Doc[] }>(`/api/projects/${pid}`) })
  const [editing, setEditing] = useState(false)
  const [connect, setConnect] = useState<null | 'google' | 'microsoft'>(null)
  const [extUrl, setExtUrl] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
  if (!q.data) return <Spinner />
  const p = q.data
  if (current?.id !== p.id) setTimeout(() => setProjectId(p.id), 0)

  const newDoc = async () => {
    const title = prompt('Document title', 'New draft'); if (!title) return
    const d = await post<Doc>(`/api/projects/${pid}/documents`, { title }); await qc.invalidateQueries(); nav(`/documents/${d.id}`)
  }
  const upload = async (f: File) => {
    const form = new FormData(); form.append('file', f); form.append('project_id', String(pid))
    try { await api('/api/integrations/word/upload', { method: 'POST', form }); await qc.invalidateQueries(); toast('Word document connected (read-only).') }
    catch (e: any) { toast(e.message, 'error') }
  }
  const connectExternal = async () => {
    try { await post('/api/integrations/documents', { project_id: pid, provider: connect, url_or_id: extUrl }); await qc.invalidateQueries(); setConnect(null); setExtUrl(''); toast('Document connected (read-only).') }
    catch (e: any) {
      if (e.status === 412) { if (confirm(`${e.message}\n\nConnect your ${connect === 'google' ? 'Google' : 'Microsoft'} account now?`)) startOAuth(connect!) }
      else toast(e.message, 'error')
    }
  }
  const startOAuth = async (provider: string) => {
    try { const r = await get<{ url: string }>(`/api/integrations/${provider}/start`); window.location.href = r.url } catch (e: any) { toast(e.message, 'error') }
  }

  return (
    <div>
      <PageHeader title={p.name} sub={<>{CAT_LABEL[p.category]} · created {timeAgo(p.created_at)}</>}
        actions={<><Button icon={<Pencil className="h-4 w-4" />} onClick={() => setEditing(true)}>Edit</Button><Button variant="primary" onClick={() => nav('/resume')}>Resume work</Button></>} />
      {p.goal && <Card className="mb-6 p-4"><div className="text-[13px] font-semibold text-muted">Goal</div><p className="mt-1">{p.goal}</p></Card>}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[15px] font-semibold">Documents</h2>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" icon={<FilePlus2 className="h-4 w-4" />} onClick={newDoc}>New document</Button>
          <Button size="sm" icon={<Link2 className="h-4 w-4" />} onClick={() => setConnect('google')}>Connect Google Doc</Button>
          <Button size="sm" icon={<Link2 className="h-4 w-4" />} onClick={() => setConnect('microsoft')}>Connect Word (OneDrive)</Button>
          <Button size="sm" icon={<Upload className="h-4 w-4" />} onClick={() => fileRef.current?.click()}>Upload .docx</Button>
          <input ref={fileRef} type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" hidden onChange={e => e.target.files?.[0] && upload(e.target.files[0])} />
        </div>
      </div>
      <div className="grid gap-2">
        {p.documents.map(d => (
          <Link key={d.id} to={`/documents/${d.id}`} className="flex items-center gap-3 rounded-lg border border-line bg-surface p-3 hover:border-fact">
            <FileText className="h-5 w-5 text-muted" aria-hidden />
            <div className="min-w-0 flex-1"><div className="truncate font-medium">{d.title}</div><div className="text-[12px] text-muted">{d.word_count} words · edited {timeAgo(d.updated_at)}</div></div>
            {d.read_only && <Pill tone="gray">{d.source === 'google_docs' ? 'Google Docs' : 'Word'} · read-only</Pill>}
          </Link>
        ))}
      </div>
      <div className="mt-6 flex flex-wrap gap-2 text-sm">
        <Link className="text-fact underline" to="/checkpoints">Checkpoints</Link><span className="text-muted">·</span>
        <Link className="text-fact underline" to="/thoughts">Unfinished thoughts</Link><span className="text-muted">·</span>
        <Link className="text-fact underline" to="/notes">Notes & references</Link><span className="text-muted">·</span>
        <Link className="text-fact underline" to="/history">Activity history</Link>
      </div>
      {editing && <Modal title="Edit project" onClose={() => setEditing(false)}><ProjectForm initial={p} onDone={() => { setEditing(false); qc.invalidateQueries() }} /></Modal>}
      {connect && (
        <Modal title={connect === 'google' ? 'Connect a Google Doc' : 'Connect a Word document'} onClose={() => setConnect(null)}>
          <p className="mb-3 text-sm text-muted">Re-Focus AI reads the document so it can show where you stopped. It never edits it — you keep writing in {connect === 'google' ? 'Google Docs' : 'Word'}.</p>
          <Label htmlFor="ext-url">{connect === 'google' ? 'Google Docs link' : 'OneDrive / SharePoint link or file ID'}</Label>
          <Input id="ext-url" value={extUrl} onChange={e => setExtUrl(e.target.value)} placeholder={connect === 'google' ? 'https://docs.google.com/document/d/…' : 'https://…sharepoint.com/… or drive item ID'} />
          <div className="mt-4 flex justify-between gap-2">
            <Button variant="ghost" onClick={() => startOAuth(connect)}>Connect {connect === 'google' ? 'Google' : 'Microsoft'} account</Button>
            <Button variant="primary" disabled={!extUrl.trim()} onClick={connectExternal}>Connect document</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}
