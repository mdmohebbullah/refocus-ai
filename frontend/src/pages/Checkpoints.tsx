/** Pause & Checkpoints (Feature 7) — list, open, compare. */
import { useQuery } from '@tanstack/react-query'
import { MapPin, Pause } from 'lucide-react'
import { get } from '../api/client'
import type { Checkpoint } from '../api/types'
import { Button, Card, Empty, PageHeader, Spinner, fmtTime } from '../components/ui'
import { useApp } from '../state/app'
import { usePanels } from '../state/panels'
import { pauseProps } from '../panels/PausePanel'

export function CheckpointsPage() {
  const { project } = useApp()
  const panels = usePanels()
  const q = useQuery({ queryKey: ['checkpoints', project?.id], enabled: !!project, queryFn: () => get<{ checkpoints: Checkpoint[] }>(`/api/projects/${project!.id}/checkpoints`) })
  if (!project) return <Empty title="No project selected" />
  const pause = <Button variant="primary" icon={<Pause className="h-4 w-4" />} onClick={() => panels.open('pause', pauseProps(project.id))}>Pause session</Button>
  return (
    <div>
      <PageHeader title="Pause & Checkpoints" sub="Each checkpoint keeps what you chose to save before a break." actions={pause} />
      {!q.data ? <Spinner /> : q.data.checkpoints.length === 0 ? <Empty title="No checkpoints yet" action={pause}>Press Pause Session before you step away. You'll review what gets saved first.</Empty> : (
        <ol className="space-y-2">
          {[...q.data.checkpoints].reverse().map(c => (
            <li key={c.id}>
              <Card className="flex cursor-pointer flex-wrap items-center gap-3 p-4 hover:border-fact" onClick={() => panels.open('checkpoint', { checkpointId: c.id })}
                role="button" tabIndex={0} onKeyDown={e => e.key === 'Enter' && panels.open('checkpoint', { checkpointId: c.id })}>
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-fact-bg text-[13px] font-bold text-fact">{c.index}</span>
                <div className="min-w-0 flex-1">
                  <div className="font-semibold">{c.label}</div>
                  {c.position?.paragraph_text && <div className="mt-0.5 flex items-center gap-1 truncate font-serif text-[13px] italic text-muted"><MapPin className="h-3.5 w-3.5 shrink-0" />…{c.position.paragraph_text.slice(-90)}</div>}
                </div>
                <div className="text-right text-[12px] text-muted">{fmtTime(c.created_at)}{c.resumed_at && <div>resumed {fmtTime(c.resumed_at)}</div>}</div>
              </Card>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
