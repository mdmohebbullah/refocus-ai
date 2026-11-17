/** Resume Workspace (Feature 10) with the checkpoint timeline slider (Feature 5B). */
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { get } from '../api/client'
import type { Checkpoint } from '../api/types'
import { ResumeCardView } from '../components/ResumeCardView'
import { Card, Empty, PageHeader, fmtTime } from '../components/ui'
import { useApp } from '../state/app'
import { NewProjectButton } from './Projects'

export function CheckpointSlider({ projectId, value, onChange }: { projectId: number; value: number | null; onChange: (id: number) => void }) {
  const q = useQuery({ queryKey: ['checkpoints', projectId], queryFn: () => get<{ checkpoints: Checkpoint[] }>(`/api/projects/${projectId}/checkpoints`) })
  const cps = q.data?.checkpoints ?? []
  if (cps.length < 2) return null
  const idx = value ? Math.max(0, cps.findIndex(c => c.id === value)) : cps.length - 1
  return (
    <div className="mb-4">
      <label htmlFor="cp-slider" className="mb-1 flex justify-between text-[12px] text-muted"><span>Checkpoint timeline</span><span>{fmtTime(cps[idx]?.created_at)}</span></label>
      <input id="cp-slider" type="range" min={0} max={cps.length - 1} step={1} value={idx} className="w-full accent-[rgb(var(--navy))]"
        aria-valuetext={`Checkpoint ${idx + 1} of ${cps.length}: ${cps[idx]?.label}`} onChange={e => onChange(cps[Number(e.target.value)].id)} />
      <div className="flex justify-between text-[11px] text-muted"><span>Oldest</span><span>Newest</span></div>
    </div>
  )
}

export function ResumePage() {
  const { project } = useApp()
  const [params, setParams] = useSearchParams()
  const cp = params.get('checkpoint') ? Number(params.get('checkpoint')) : null
  if (!project) return <Empty title="No project yet" action={<NewProjectButton variant="primary" />}>Create a project first.</Empty>
  const go = (id: number) => setParams({ checkpoint: String(id) })
  return (
    <div className="mx-auto max-w-[760px]">
      <PageHeader title="Resume Workspace" sub={<>Pick up where you left off in <strong className="text-ink">{project.name}</strong>.</>} />
      <CheckpointSlider projectId={project.id} value={cp} onChange={go} />
      <Card className="p-5"><ResumeCardView projectId={project.id} checkpointId={cp} onNavigateCheckpoint={go} /></Card>
    </div>
  )
}
