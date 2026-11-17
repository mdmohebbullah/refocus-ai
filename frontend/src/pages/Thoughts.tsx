/** Unfinished Thoughts (Feature 8). */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Lightbulb, Pin, Search } from 'lucide-react'
import { get } from '../api/client'
import type { Thought } from '../api/types'
import { Button, Card, Empty, Input, PageHeader, Pill, Spinner, timeAgo } from '../components/ui'
import { useApp } from '../state/app'
import { usePanels } from '../state/panels'

export function ThoughtsPage() {
  const { project } = useApp()
  const panels = usePanels()
  const [q, setQ] = useState('')
  const [done, setDone] = useState(false)
  const list = useQuery({ queryKey: ['thoughts', project?.id, q, done], enabled: !!project,
    queryFn: () => get<{ thoughts: Thought[] }>(`/api/thoughts?project_id=${project!.id}&q=${encodeURIComponent(q)}&include_completed=${done}`) })
  if (!project) return <Empty title="No project selected" />
  const add = <Button variant="primary" icon={<Lightbulb className="h-4 w-4" />} onClick={() => panels.open('thought', { projectId: project.id })}>Quick capture</Button>
  return (
    <div>
      <PageHeader title="Unfinished Thoughts" sub="Ideas you parked, in your own words." actions={add} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative min-w-[220px] flex-1"><Search className="absolute left-3 top-3 h-4 w-4 text-muted" aria-hidden />
          <Input aria-label="Search thoughts" className="pl-9" placeholder="Search previous thoughts" value={q} onChange={e => setQ(e.target.value)} /></div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-[rgb(var(--navy))]" checked={done} onChange={e => setDone(e.target.checked)} />Show completed</label>
      </div>
      {!list.data ? <Spinner /> : list.data.thoughts.length === 0 ? <Empty title="No thoughts here" action={add} /> : (
        <div className="grid gap-3 md:grid-cols-2">
          {list.data.thoughts.map(t => (
            <Card key={t.id} className="cursor-pointer p-4 hover:border-fact" role="button" tabIndex={0}
              onClick={() => panels.open('thought', { projectId: project.id, thoughtId: t.id })} onKeyDown={e => e.key === 'Enter' && panels.open('thought', { projectId: project.id, thoughtId: t.id })}>
              <div className="mb-2 flex flex-wrap items-center gap-2 text-[12px] text-muted">
                {t.pinned && <Pill tone="blue"><Pin className="h-3 w-3" />Pinned</Pill>}
                {t.completed && <Pill tone="green">Completed</Pill>}
                {t.origin === 'voice' && <Pill>Voice</Pill>}
                <span>{timeAgo(t.created_at)}</span>
              </div>
              <p className="line-clamp-3">{t.thinking || t.next_plan || t.missing}</p>
              {t.missing && <p className="mt-2 line-clamp-2 text-[13px] text-muted">Missing: {t.missing}</p>}
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
