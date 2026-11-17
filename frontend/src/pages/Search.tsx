/** Feature 21 — Smart Search across approved saved context. Stored matches and AI-inferred matches are kept apart. */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'
import { get } from '../api/client'
import type { Provenance } from '../api/types'
import { Card, Empty, Input, PageHeader, Pill, ProvBadge, Spinner, fmtTime, shortUrl } from '../components/ui'
import { useApp } from '../state/app'
import { usePanels } from '../state/panels'

interface Result { type: string; id: number; project_id: number | null; project: string | null; title: string; url?: string; snippet?: string; at: string; match: string; match_label: string; provenance: Provenance }
const tz = -new Date().getTimezoneOffset()
const EXAMPLES = ['Find the research article I opened yesterday.', 'Show my unfinished ideas about the literature review.', 'Which sources did I save for the discussion section?']
const TYPE_LABEL: Record<string, string> = { thought: 'Thought', note: 'Note', reference: 'Reference', activity: 'Visited page', checkpoint: 'Checkpoint', task: 'Task', document: 'Document' }

export function SearchPage() {
  const [text, setText] = useState('')
  const [q, setQ] = useState('')
  const [allProjects, setAll] = useState(true)
  const { project } = useApp()
  const panels = usePanels()
  const nav = useNavigate()
  const res = useQuery({ queryKey: ['search', q, allProjects], enabled: !!q,
    queryFn: () => get<{ results: Result[]; ai_inferred: Result[]; interpreted: any; ai_provider: string | null }>(`/api/search?q=${encodeURIComponent(q)}&tz_offset_minutes=${tz}${!allProjects && project ? `&project_id=${project.id}` : ''}`) })

  const open = (r: Result) => {
    if (r.type === 'thought' && r.project_id) panels.open('thought', { projectId: r.project_id, thoughtId: r.id })
    else if (r.type === 'checkpoint') panels.open('checkpoint', { checkpointId: r.id })
    else if (r.type === 'document') nav(`/documents/${r.id}`)
    else if (r.url) panels.open('source', { title: r.title, url: r.url, kind: TYPE_LABEL[r.type] })
    else if (r.type === 'note') nav('/notes')
  }
  const row = (r: Result, inferred = false) => (
    <li key={r.type + r.id}>
      <button onClick={() => open(r)} className="flex w-full flex-wrap items-center gap-2 rounded-lg border border-line bg-surface p-3 text-left hover:border-fact">
        <Pill>{TYPE_LABEL[r.type] ?? r.type}</Pill>
        <div className="min-w-0 flex-1"><div className="truncate font-medium">{r.title}</div>
          <div className="truncate text-[12px] text-muted">{r.url ? shortUrl(r.url) : r.snippet}{r.project && ` · ${r.project}`} · {fmtTime(r.at)}</div></div>
        <ProvBadge kind={r.provenance} />
      </button>
      {inferred && <p className="ml-2 mt-1 text-[11px] text-guess">{r.match_label}</p>}
    </li>
  )
  return (
    <div className="mx-auto max-w-[860px]">
      <PageHeader title="Smart Search" sub="Ask in your own words. Searches only what you saved or approved." />
      <form onSubmit={e => { e.preventDefault(); setQ(text.trim()) }} className="relative mb-2">
        <Search className="absolute left-3.5 top-3.5 h-5 w-5 text-muted" aria-hidden />
        <Input id="smart-search" aria-label="Search" className="h-12 pl-11 text-[15px]" placeholder="e.g. the article I opened yesterday" value={text} onChange={e => setText(e.target.value)} />
      </form>
      <div className="mb-6 flex flex-wrap items-center gap-2 text-[13px]">
        {EXAMPLES.map(x => <button key={x} className="rounded-full border border-line px-3 py-1 text-muted hover:text-ink" onClick={() => { setText(x); setQ(x) }}>{x}</button>)}
        {project && <label className="ml-auto flex items-center gap-1.5"><input type="checkbox" className="accent-[rgb(var(--navy))]" checked={!allProjects} onChange={e => setAll(!e.target.checked)} />Only {project.name}</label>}
      </div>
      {!q ? null : !res.data ? <Spinner label="Searching" /> : (
        <div className="space-y-6">
          <p className="text-[12px] text-muted">
            Understood as: {res.data.interpreted.terms.length ? <>words “{res.data.interpreted.terms.join(' ')}”</> : 'any words'}
            {res.data.interpreted.types.length ? <> · types: {res.data.interpreted.types.map((t: string) => TYPE_LABEL[t] ?? t).join(', ')}</> : null}
            {res.data.interpreted.since && <> · since {fmtTime(res.data.interpreted.since)}</>}
            {res.data.interpreted.project && <> · project: {res.data.interpreted.project}</>}
          </p>
          <section>
            <h2 className="mb-2 text-[15px] font-semibold">Matches in your saved records <span className="font-normal text-muted">({res.data.results.length})</span></h2>
            {res.data.results.length === 0 ? <Empty title="No stored matches" /> : <ul className="space-y-2">{res.data.results.slice(0, 30).map(r => row(r))}</ul>}
          </section>
          {res.data.ai_inferred.length > 0 && (
            <section>
              <h2 className="mb-1 text-[15px] font-semibold">AI-inferred associations <span className="font-normal text-muted">({res.data.ai_inferred.length})</span></h2>
              <p className="mb-2 text-[12px] text-muted">Found through related terms the AI suggested. These may not be what you meant.</p>
              <Card className="border-dashed border-guess/50 p-2"><ul className="space-y-2">{res.data.ai_inferred.map(r => row(r, true))}</ul></Card>
            </section>
          )}
        </div>
      )}
    </div>
  )
}
