/** The built-in writing editor (TipTap), plus a read-only view for connected Google Docs / Word documents. */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { EditorContent, Extension, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'
import { ArrowLeft, Bold, ExternalLink, GitCompare, Heading2, Italic, Lightbulb, List, RefreshCw } from 'lucide-react'
import { get, patch, post } from '../api/client'
import type { Doc } from '../api/types'
import { Button, Pill, Spinner, cx, timeAgo } from '../components/ui'
import { editorBridge, useApp } from '../state/app'
import { usePanels } from '../state/panels'

const resumeKey = new PluginKey('resumeMark')
/** Temporarily highlights the sentence where the user stopped. */
const ResumeMark = Extension.create({
  name: 'resumeMark',
  addProseMirrorPlugins() {
    return [new Plugin({
      key: resumeKey,
      state: {
        init: () => DecorationSet.empty,
        apply(tr, set) {
          const meta = tr.getMeta(resumeKey)
          if (meta === null) return DecorationSet.empty
          if (meta) return DecorationSet.create(tr.doc, [Decoration.inline(meta.from, meta.to, { class: 'rf-resume-mark' })])
          return set.map(tr.mapping, tr.doc)
        },
      },
      props: { decorations(state) { return resumeKey.getState(state) } },
    })]
  },
})

function findText(doc: any, needle: string): { from: number; to: number } | null {
  if (!needle) return null
  const probe = needle.trim().slice(-80)
  let hit: { from: number; to: number } | null = null
  doc.descendants((node: any, pos: number) => {
    if (hit || !node.isTextblock) return !hit
    const i = node.textContent.indexOf(probe)
    if (i >= 0) hit = { from: pos + 1 + i, to: pos + 1 + i + probe.length }
    return false
  })
  return hit
}

export function EditorPage() {
  const { id } = useParams()
  const docId = Number(id)
  const q = useQuery({ queryKey: ['document', docId], queryFn: () => get<Doc>(`/api/documents/${docId}`), staleTime: Infinity, refetchOnWindowFocus: false })
  if (!q.data) return <Spinner label="Opening your document" />
  return q.data.read_only ? <ExternalDocView doc={q.data} /> : <BuiltinEditor doc={q.data} />
}

function BuiltinEditor({ doc }: { doc: Doc }) {
  const [params, setParams] = useSearchParams()
  const qc = useQueryClient()
  const panels = usePanels()
  const { toast } = useApp()
  const [status, setStatus] = useState<'saved' | 'saving' | 'unsaved' | 'error'>('saved')
  const [title, setTitle] = useState(doc.title)
  const timer = useRef<number | null>(null)
  const pending = useRef<any>(null)

  const flush = useCallback(async () => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null }
    const body = pending.current
    if (!body) return
    pending.current = null
    setStatus('saving')
    try { await patch(`/api/documents/${doc.id}`, body); setStatus('saved') } catch { setStatus('error'); pending.current = body }
  }, [doc.id])

  const schedule = useCallback((body: any, delay = 1200) => {
    pending.current = { ...(pending.current ?? {}), ...body }
    setStatus('unsaved')
    if (timer.current) clearTimeout(timer.current)
    timer.current = window.setTimeout(flush, delay)
  }, [flush])

  const editor = useEditor({
    extensions: [StarterKit, Placeholder.configure({ placeholder: 'Start writing…' }), ResumeMark],
    content: doc.content_json ?? (doc.content_text ? `<p>${doc.content_text}</p>` : ''),
    editorProps: { attributes: { 'aria-label': `Document: ${doc.title}`, role: 'textbox', 'aria-multiline': 'true' } },
    onUpdate: ({ editor }) => schedule({ content_json: editor.getJSON(), content_text: editor.getText({ blockSeparator: '\n\n' }), cursor_pos: editor.state.selection.from }),
    onSelectionUpdate: ({ editor }) => { if (!pending.current) schedule({ cursor_pos: editor.state.selection.from }, 4000); else pending.current.cursor_pos = editor.state.selection.from },
  })

  // Bridge for Pause Session and thought linking.
  useEffect(() => {
    if (!editor) return
    editorBridge.docId = doc.id
    editorBridge.flush = flush
    editorBridge.getPosition = () => {
      const { $from, from } = editor.state.selection
      const before = $from.parent.textBetween(0, $from.parentOffset, ' ')
      return { cursor: from, paragraph_text: before.trim() ? before : $from.parent.textContent, paragraph_index: $from.index(0) }
    }
    return () => { editorBridge.docId = null; editorBridge.getPosition = null; editorBridge.flush = null; flush() }
  }, [editor, doc.id, flush])

  // Resume Writing: restore cursor and highlight where the user stopped.
  useEffect(() => {
    if (!editor) return
    const cursor = params.get('cursor'); const hl = params.get('highlight')
    const target = Number(cursor || doc.cursor_pos || 0)
    const size = editor.state.doc.content.size
    const range = hl ? findText(editor.state.doc, hl) : null
    const pos = Math.min(Math.max(1, range ? range.to : target || size), size)
    editor.chain().focus().setTextSelection(pos).scrollIntoView().run()
    if (range) {
      editor.view.dispatch(editor.state.tr.setMeta(resumeKey, range))
      const t = window.setTimeout(() => editor.view.dispatch(editor.state.tr.setMeta(resumeKey, null)), 6000)
      if (cursor !== null || hl !== null) setParams({}, { replace: true })
      return () => clearTimeout(t)
    }
  }, [editor]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const h = (e: BeforeUnloadEvent) => { if (pending.current) { flush(); e.preventDefault() } }
    window.addEventListener('beforeunload', h)
    return () => window.removeEventListener('beforeunload', h)
  }, [flush])

  const saveTitle = async () => { if (title.trim() && title !== doc.title) { await patch(`/api/documents/${doc.id}`, { title }); qc.invalidateQueries(); toast('Title saved.') } }
  const tool = (label: string, icon: React.ReactNode, run: () => void, active?: boolean) =>
    <button type="button" aria-label={label} title={label} aria-pressed={active} onClick={run} className={cx('rounded p-2 hover:bg-canvas', active && 'bg-fact-bg text-fact')}>{icon}</button>

  return (
    <div className="mx-auto max-w-[760px]">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Link to={`/projects/${doc.project_id}`} className="rounded p-1.5 hover:bg-canvas" aria-label="Back to project"><ArrowLeft className="h-4 w-4" /></Link>
        <input aria-label="Document title" value={title} onChange={e => setTitle(e.target.value)} onBlur={saveTitle}
          className="min-w-0 flex-1 bg-transparent text-xl font-bold outline-none focus:underline" />
        <span className="text-[12px] text-muted" role="status">{{ saved: 'Saved', saving: 'Saving…', unsaved: 'Unsaved changes', error: 'Not saved — retrying' }[status]}</span>
      </div>
      <div className="sticky top-0 z-10 mb-4 flex flex-wrap items-center gap-1 rounded-lg border border-line bg-surface px-2 py-1">
        {editor && <>
          {tool('Bold', <Bold className="h-4 w-4" />, () => editor.chain().focus().toggleBold().run(), editor.isActive('bold'))}
          {tool('Italic', <Italic className="h-4 w-4" />, () => editor.chain().focus().toggleItalic().run(), editor.isActive('italic'))}
          {tool('Heading', <Heading2 className="h-4 w-4" />, () => editor.chain().focus().toggleHeading({ level: 2 }).run(), editor.isActive('heading'))}
          {tool('Bulleted list', <List className="h-4 w-4" />, () => editor.chain().focus().toggleBulletList().run(), editor.isActive('bulletList'))}
        </>}
        <div className="ml-auto flex gap-1">
          <Button size="sm" variant="ghost" icon={<Lightbulb className="h-4 w-4" />} onClick={() => panels.open('thought', { projectId: doc.project_id })}>Thought</Button>
          <Button size="sm" variant="ghost" icon={<GitCompare className="h-4 w-4" />} onClick={async () => { await flush(); panels.open('compare', { documentId: doc.id, b: 'current' }) }}>Compare versions</Button>
        </div>
      </div>
      <div className="rf-editor rounded-lg border border-line bg-surface px-6 py-8 sm:px-12"><EditorContent editor={editor} /></div>
    </div>
  )
}

function ExternalDocView({ doc }: { doc: Doc }) {
  const [params] = useSearchParams()
  const qc = useQueryClient()
  const { toast } = useApp()
  const panels = usePanels()
  const [busy, setBusy] = useState(false)
  const hl = params.get('highlight') ?? ''
  const paras = (doc.content_text ?? '').split(/\n{2,}|\n/).filter(p => p.trim())
  useEffect(() => {
    editorBridge.docId = doc.id
    editorBridge.getPosition = null
    setTimeout(() => document.getElementById('rf-hl')?.scrollIntoView({ block: 'center' }), 50)
    return () => { editorBridge.docId = null }
  }, [doc.id])
  const refresh = async () => {
    setBusy(true)
    try { await post(`/api/integrations/documents/${doc.id}/refresh`); await qc.invalidateQueries({ queryKey: ['document', doc.id] }); toast('Read the latest version.') }
    catch (e: any) { toast(e.message, 'error') } finally { setBusy(false) }
  }
  const app = doc.source === 'google_docs' ? 'Google Docs' : 'Word'
  return (
    <div className="mx-auto max-w-[760px]">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Link to={`/projects/${doc.project_id}`} className="rounded p-1.5 hover:bg-canvas" aria-label="Back to project"><ArrowLeft className="h-4 w-4" /></Link>
        <h1 className="min-w-0 flex-1 truncate font-hand text-[34px] font-bold leading-none">{doc.title}</h1>
        <Pill tone="gray">{app} · read-only</Pill>
      </div>
      <div className="mb-4 flex flex-wrap gap-2 rounded-lg border border-line bg-surface p-3 text-sm">
        <span className="flex-1 text-muted">Re-Focus AI reads this document but never edits it. Last read {timeAgo(doc.updated_at)}.</span>
        <Button size="sm" icon={<RefreshCw className="h-4 w-4" />} loading={busy} onClick={refresh}>Read latest</Button>
        <Button size="sm" icon={<GitCompare className="h-4 w-4" />} onClick={() => panels.open('compare', { documentId: doc.id, b: 'current' })}>Compare snapshots</Button>
        {doc.external_url && <a href={doc.external_url} target="_blank" rel="noopener noreferrer" className="inline-flex h-8 items-center gap-1.5 rounded-md bg-navy px-3 text-[13px] font-semibold text-[rgb(var(--on-navy))]"><ExternalLink className="h-4 w-4" />Open in {app}</a>}
      </div>
      <div className="rounded-lg border border-line bg-surface px-6 py-8 font-serif text-[17px] leading-[1.75] sm:px-12">
        {paras.length === 0 && <p className="text-muted">No text could be read from this document yet.</p>}
        {paras.map((p, i) => {
          const hit = hl && p.includes(hl.trim().slice(-60))
          return <p key={i} id={hit ? 'rf-hl' : undefined} className={cx('mb-4', hit && 'rf-resume-mark rounded bg-fact-bg px-1')}>{p}</p>
        })}
      </div>
    </div>
  )
}
