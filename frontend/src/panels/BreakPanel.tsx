/** Feature 17 — Smart Break Detection prompt. Unobtrusive and can be turned off in Settings. */
import { patch } from '../api/client'
import { Button } from '../components/ui'
import { useApp } from '../state/app'
import { usePanels } from '../state/panels'
import { pauseProps } from './PausePanel'
import { snoozeBreak } from '../hooks/useBreakDetection'

export function BreakPanel({ projectId, idleMinutes }: { projectId: number; idleMinutes: number }) {
  const panels = usePanels()
  const { refreshMe, toast } = useApp()
  return (
    <div className="space-y-4">
      <p className="text-[15px]">Would you like to save your current progress before leaving?</p>
      <p className="text-[13px] text-muted">No input in Re-Focus AI for {idleMinutes} minutes. Nothing has been captured automatically.</p>
      <div className="grid gap-2">
        <Button variant="primary" onClick={() => panels.open('pause', pauseProps(projectId))}>Save checkpoint</Button>
        <Button onClick={() => { snoozeBreak(0); panels.close() }}>Continue working</Button>
        <Button onClick={() => { snoozeBreak(15); panels.close(); toast('I’ll ask again in 15 minutes.', 'info') }}>Remind me later</Button>
        <Button variant="ghost" onClick={() => { snoozeBreak(24 * 60); panels.close() }}>Dismiss</Button>
      </div>
      <button className="text-[13px] text-fact underline" onClick={async () => { await patch('/api/me/preferences', { break_reminders: false }); await refreshMe(); panels.close(); toast('Break reminders turned off. You can turn them on in Settings.', 'info') }}>
        Turn off break reminders
      </button>
    </div>
  )
}
