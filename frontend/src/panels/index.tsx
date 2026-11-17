import type { ComponentType } from 'react'
import type { PanelType } from '../state/panels'
import { PausePanel } from './PausePanel'
import { ResumePanel, WhyPanel, SourcePanel, HelpPanel, ReviewPanel } from './ReviewPanels'
import { ThoughtPanel } from './ThoughtPanel'
import { CheckpointPanel, ComparePanel } from './CheckpointPanels'
import { BreakPanel } from './BreakPanel'

export const PANELS: Record<PanelType, { title: (p: any) => string; component: ComponentType<any> }> = {
  pause: { title: () => 'Pause session', component: PausePanel },
  thought: { title: p => (p.thoughtId ? 'Unfinished thought' : 'New unfinished thought'), component: ThoughtPanel },
  resume: { title: () => 'Focus Resume Card', component: ResumePanel },
  why: { title: () => 'Why this suggestion?', component: WhyPanel },
  source: { title: p => (p.list ? 'Review sources' : p.title || 'Source'), component: SourcePanel },
  help: { title: () => 'Help level', component: HelpPanel },
  review: { title: () => 'Review suggestion', component: ReviewPanel },
  checkpoint: { title: () => 'Checkpoint', component: CheckpointPanel },
  compare: { title: () => 'Compare versions', component: ComparePanel },
  break: { title: () => 'Taking a break?', component: BreakPanel },
}
