/** Feature 3 — Browser Tab Selection. Users decide which tabs may contribute to AI context. */
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Ban, CheckSquare, Eye, FileText, Square } from 'lucide-react'
import { get, patch, post } from '../api/client'
import type { Tab } from '../api/types'
import { Button, Card, Empty, PageHeader, Pill, Spinner, cx, shortUrl } from '../components/ui'
import { useApp } from '../state/app'

export function TabsPage() {
  const { project, projects, toast } = useApp()
  const qc = useQueryClient()
  const [reviewOnly, setReviewOnly] = useState(false)
  const q = useQuery({ queryKey: ['tabs'], queryFn: () => get<{ tabs: Tab[]; collection: string; remember_preferences: boolean }>('/api/tabs'), refetchInterval: 15_000 })
  if (!q.data) return <Spinner />
  const tabs = q.data.tabs.filter(t => !reviewOnly || t.selected)
  const selectable = q.data.tabs.filter(t => !t.excluded)
  const sel = async (ids: number[], selected: boolean, project_id?: number | null) => {
    await post('/api/tabs/select', { tab_ids: ids, selected, project_id: project_id ?? null }); qc.invalidateQueries({ queryKey: ['tabs'] })
  }
  const exclude = async (t: Tab) => {
    if (!confirm(`Exclude ${t.domain}? Its tabs and recorded visits are removed and it will never be collected again.`)) return
    await post('/api/tabs/exclude-site', { domain: t.domain }); qc.invalidateQueries(); toast(`${t.domain} is excluded.`)
  }
  const remember = async (v: boolean) => { await patch('/api/privacy', { remember_tab_preferences: v }); qc.invalidateQueries({ queryKey: ['tabs'] }) }
  const projName = (id: number | null) => projects.find(p => p.id === id)?.name

  return (
    <div>
      <PageHeader title="Browser Tabs" sub="Choose which open tabs Re-Focus AI may use. Unselected and excluded tabs never reach the AI."
        actions={<>
          <Button size="sm" icon={<CheckSquare className="h-4 w-4" />} onClick={() => sel(selectable.map(t => t.id), true, project?.id)} disabled={!selectable.length}>Select all</Button>
          <Button size="sm" icon={<Square className="h-4 w-4" />} onClick={() => sel(selectable.map(t => t.id), false)} disabled={!selectable.length}>Deselect all</Button>
          <Button size="sm" variant={reviewOnly ? 'selected' : 'secondary'} icon={<Eye className="h-4 w-4" />} onClick={() => setReviewOnly(!reviewOnly)}>Review selected tabs</Button>
        </>} />
      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
        <Pill tone={q.data.collection === 'on' ? 'green' : 'gray'}>Collection: {q.data.collection === 'on' ? 'on' : q.data.collection === 'private_mode' ? 'private mode' : 'off'}</Pill>
        <label className="flex items-center gap-2"><input type="checkbox" className="accent-[rgb(var(--navy))]" checked={q.data.remember_preferences} onChange={e => remember(e.target.checked)} />Remember approved websites</label>
        <span className="text-muted">Page titles and addresses are read separately from page content; content needs extra permission in the extension.</span>
      </div>
      {q.data.tabs.length === 0 ? (
        <Empty title="No tabs from the extension yet">Install the Re-Focus AI extension and pair it in <Link className="text-fact underline" to="/settings">Settings & Privacy</Link>. Your open tabs will appear here.</Empty>
      ) : (
        <Card>
          <ul className="divide-y divide-line">
            {tabs.map(t => (
              <li key={t.id} className={cx('flex flex-wrap items-center gap-3 px-4 py-3', t.excluded && 'opacity-60')}>
                <input type="checkbox" aria-label={t.excluded ? 'Excluded tab' : `Use “${t.title}”`} className="h-4 w-4 accent-[rgb(var(--navy))]"
                  disabled={t.excluded} checked={t.selected} onChange={e => sel([t.id], e.target.checked, e.target.checked ? project?.id : null)} />
                {t.fav_icon_url && !t.excluded ? <img src={t.fav_icon_url} alt="" className="h-4 w-4" /> : <span className="h-4 w-4 rounded bg-canvas" aria-hidden />}
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{t.excluded ? 'Excluded website — details hidden' : t.title}</div>
                  <div className="truncate text-[12px] text-muted">{t.excluded ? t.domain : shortUrl(t.url)}</div>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  {t.status !== 'complete' && <Pill>{t.status}</Pill>}
                  {t.content_available && <Pill tone="blue"><FileText className="h-3 w-3" />Page content shared</Pill>}
                  {t.excluded ? <Pill tone="gray">Excluded</Pill> : t.selected ? <Pill tone="blue">Selected</Pill> : <Pill tone="gray">Not used</Pill>}
                  {projName(t.project_id) && <Pill>{projName(t.project_id)}</Pill>}
                </div>
                {!t.excluded && <Button size="sm" variant="ghost" icon={<Ban className="h-3.5 w-3.5" />} onClick={() => exclude(t)}>Exclude website</Button>}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
