/** Settings & Privacy (Feature 23) — personalization, privacy, devices, connected accounts, export and deletion. */
import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { Copy, Download, KeyRound, Laptop, Link2, Shield, Trash2 } from 'lucide-react'
import { API_BASE, del, get, getToken, patch, post } from '../api/client'
import { Button, Card, Check, Input, Label, PageHeader, Pill, SectionTitle, Spinner, fmtTime } from '../components/ui'
import { useApp } from '../state/app'
import { comboFromEvent } from '../hooks/useShortcuts'

interface Privacy {
  private_mode: boolean; activity_collection: boolean; excluded_domains: string[]; removed_default_exclusions: string[]
  effective_exclusions: string[]; default_categories: Record<string, string[]>; always_excluded: string[]
  remember_tab_preferences: boolean; approved_domains: string[]; history_retention_days: number; deletion_notes: string[]; ai_provider: string
}
const SHORTCUT_LABEL: Record<string, string> = { pause_session: 'Pause session', resume_session: 'Resume session', save_thought: 'Save thought',
  save_checkpoint: 'Save checkpoint', panel_back: 'Panel back', panel_forward: 'Panel forward', older_checkpoint: 'Older checkpoint',
  newer_checkpoint: 'Newer checkpoint', search: 'Search' }

export function SettingsPage() {
  const { me, refreshMe, toast, signOut } = useApp()
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const priv = useQuery({ queryKey: ['privacy'], queryFn: () => get<Privacy>('/api/privacy') })
  const devices = useQuery({ queryKey: ['devices'], queryFn: () => get<{ devices: any[] }>('/api/devices') })
  const accounts = useQuery({ queryKey: ['accounts'], queryFn: () => get<{ accounts: any[]; configured: Record<string, boolean>; access: string }>('/api/integrations/accounts') })
  const [newDomain, setNewDomain] = useState('')
  const [token, setToken] = useState<string | null>(null)
  const [devName, setDevName] = useState('My Chrome')
  const [recording, setRecording] = useState<string | null>(null)
  const [delPw, setDelPw] = useState(''), [delConfirm, setDelConfirm] = useState('')

  useEffect(() => {
    const c = params.get('connected'), e = params.get('connect_error')
    if (c) toast(`${c === 'google' ? 'Google' : 'Microsoft'} account connected (read-only).`)
    if (e) toast(`Couldn't connect: ${e}`, 'error')
    if (c || e) setParams({}, { replace: true })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!recording) return
    const h = async (e: KeyboardEvent) => {
      e.preventDefault()
      const combo = comboFromEvent(e); if (!combo) return
      setRecording(null)
      try { await patch('/api/me/preferences', { shortcuts: { [recording]: combo } }); await refreshMe(); toast(`${SHORTCUT_LABEL[recording]}: ${combo}`) }
      catch (x: any) { toast(x.message, 'error') }
    }
    window.addEventListener('keydown', h, { capture: true })
    return () => window.removeEventListener('keydown', h, { capture: true })
  }, [recording, refreshMe, toast])

  if (!me || !priv.data) return <Spinner />
  const p = priv.data, prefs = me.preferences
  const setPrivacy = async (body: Partial<Privacy>) => { await patch('/api/privacy', body); await qc.invalidateQueries(); await refreshMe() }
  const setPref = async (body: any) => { await patch('/api/me/preferences', body); await refreshMe(); await qc.invalidateQueries({ queryKey: ['resume'] }) }
  const exportData = async () => {
    const res = await fetch(`${API_BASE}/api/privacy/export`, { headers: { Authorization: `Bearer ${getToken()}` } })
    const blob = new Blob([JSON.stringify(await res.json(), null, 2)], { type: 'application/json' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `refocus-ai-export-${new Date().toISOString().slice(0, 10)}.json`; a.click()
  }
  const pair = async () => { const r = await post('/api/devices', { name: devName }); setToken(r.token); qc.invalidateQueries({ queryKey: ['devices'] }) }
  const removedDefaults = new Set(p.removed_default_exclusions)

  return (
    <div className="space-y-6">
      <PageHeader title="Settings & Privacy" sub="You decide what Re-Focus AI collects, keeps and uses." />

      <Card className="p-5">
        <SectionTitle><span className="flex items-center gap-2"><Shield className="h-4 w-4" />Privacy</span></SectionTitle>
        <div className="grid gap-1 md:grid-cols-2">
          <Check checked={p.private_mode} onChange={v => setPrivacy({ private_mode: v })}><strong>Private mode</strong><span className="block text-[13px] text-muted">Collect nothing from any browser and keep browser data out of AI suggestions.</span></Check>
          <Check checked={p.activity_collection} onChange={v => setPrivacy({ activity_collection: v })}><strong>Browser activity collection</strong><span className="block text-[13px] text-muted">Tabs and last-60-minutes history from paired browsers.</span></Check>
          <Check checked={p.remember_tab_preferences} onChange={v => setPrivacy({ remember_tab_preferences: v })}><strong>Remember approved websites</strong><span className="block text-[13px] text-muted">New tabs from sites you approved are selected automatically.</span></Check>
          <div><Label htmlFor="ret">Keep browser history for</Label>
            <select id="ret" value={p.history_retention_days} onChange={e => setPrivacy({ history_retention_days: Number(e.target.value) })} className="h-10 rounded-md border border-line bg-surface px-2 text-sm">
              {[1, 7, 14, 30, 90, 365].map(d => <option key={d} value={d}>{d} day{d > 1 ? 's' : ''}</option>)}</select></div>
        </div>

        <div className="mt-5 border-t border-line pt-4">
          <div className="mb-2 text-sm font-semibold">Website exclusion list</div>
          <p className="mb-3 text-[13px] text-muted">Excluded sites never contribute titles, addresses or content. Always excluded: {p.always_excluded.join('; ')}.</p>
          <form className="mb-3 flex gap-2" onSubmit={async e => { e.preventDefault(); if (!newDomain.trim()) return; await setPrivacy({ excluded_domains: [...p.excluded_domains, newDomain] }); setNewDomain('') }}>
            <Input aria-label="Website to exclude" placeholder="example.com" value={newDomain} onChange={e => setNewDomain(e.target.value)} /><Button type="submit">Exclude</Button>
          </form>
          {p.excluded_domains.length > 0 && <div className="mb-3 flex flex-wrap gap-1.5">{p.excluded_domains.map(d => (
            <Pill key={d}>{d}<button aria-label={`Stop excluding ${d}`} className="ml-1" onClick={() => setPrivacy({ excluded_domains: p.excluded_domains.filter(x => x !== d) })}>×</button></Pill>))}</div>}
          <details><summary className="cursor-pointer text-[13px] font-semibold">Sensitive sites excluded by default</summary>
            <div className="mt-2 grid gap-3 md:grid-cols-2">{Object.entries(p.default_categories).map(([cat, ds]) => (
              <div key={cat}><div className="mb-1 text-[13px] font-semibold">{cat}</div><div className="flex flex-wrap gap-1">{ds.map(d => (
                <button key={d} onClick={() => setPrivacy({ removed_default_exclusions: removedDefaults.has(d) ? [...removedDefaults].filter(x => x !== d) : [...removedDefaults, d] })}
                  className={'rounded-full border px-2 py-0.5 text-[12px] ' + (removedDefaults.has(d) ? 'border-line text-muted line-through' : 'border-fact/30 bg-fact-bg text-fact')}
                  aria-pressed={!removedDefaults.has(d)} title={removedDefaults.has(d) ? 'Click to exclude again' : 'Click to allow'}>{d}</button>))}</div></div>))}</div></details>
        </div>
      </Card>

      <Card className="p-5">
        <SectionTitle><span className="flex items-center gap-2"><Laptop className="h-4 w-4" />Browser extension & devices</span></SectionTitle>
        <p className="mb-3 text-[13px] text-muted">Your projects, checkpoints and notes sync to every device where you sign in. Browser data is only collected on browsers you pair here, and each one can be turned off.</p>
        <div className="mb-4 rounded-lg border-2 border-dashed border-ink/40 bg-canvas p-4 text-sm">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <span className="font-semibold">Get the Chrome extension (optional, lets Re-Focus AI see the tabs you choose)</span>
            <a href="/refocus-ai-extension.zip" download className="inline-flex h-9 items-center gap-2 rounded-md border-2 border-ink bg-navy px-3 font-semibold text-[rgb(var(--on-navy))] sketch-sm">
              <Download className="h-4 w-4" />Download the extension</a>
          </div>
          <ol className="list-decimal space-y-1 pl-5 text-[14px]">
            <li>Unzip the downloaded file (double-click it).</li>
            <li>In Chrome, open <code className="rounded bg-surface px-1">chrome://extensions</code>, turn on <b>Developer mode</b> (top right), click <b>Load unpacked</b> and choose the unzipped folder.</li>
            <li>Below, press <b>Create device token</b> and copy it.</li>
            <li>Click the Re-Focus AI icon in Chrome's toolbar (puzzle piece, then pin), paste the token and press <b>Pair this browser</b>.</li>
          </ol>
        </div>
        <ul className="mb-4 divide-y divide-line">
          {devices.data?.devices.map(d => (
            <li key={d.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
              <span className="min-w-0 flex-1 font-medium">{d.name}<span className="block text-[12px] font-normal text-muted">Last seen {d.last_seen_at ? fmtTime(d.last_seen_at) : 'never'}</span></span>
              <label className="flex items-center gap-1.5 text-[13px]"><input type="checkbox" className="accent-[rgb(var(--navy))]" checked={d.collection_enabled} onChange={async e => { await patch(`/api/devices/${d.id}`, { collection_enabled: e.target.checked }); qc.invalidateQueries({ queryKey: ['devices'] }) }} />Collection on</label>
              <Pill tone={d.content_access ? 'blue' : 'gray'}>{d.content_access ? 'Page text shared' : 'Titles & addresses only'}</Pill>
              <Button size="sm" variant="danger" onClick={async () => { if (confirm(`Unpair ${d.name}? Its open-tab list is removed.`)) { await del(`/api/devices/${d.id}`); qc.invalidateQueries({ queryKey: ['devices'] }) } }}>Unpair</Button>
            </li>
          ))}
        </ul>
        {token ? (
          <div className="rounded-lg border border-fact/40 bg-fact-bg/60 p-3 text-sm">
            <div className="mb-1 font-semibold">Device token — shown only once</div>
            <div className="flex gap-2"><code className="min-w-0 flex-1 truncate rounded bg-surface px-2 py-1.5 text-[12px]">{token}</code>
              <Button size="sm" icon={<Copy className="h-3.5 w-3.5" />} onClick={() => { navigator.clipboard?.writeText(token); toast('Token copied.') }}>Copy</Button></div>
            <p className="mt-2 text-[13px] text-muted">Open the Re-Focus AI extension, paste this token, and press “Pair this browser”.</p>
          </div>
        ) : (
          <div className="flex flex-wrap items-end gap-2"><div><Label htmlFor="dev">Name this browser</Label><Input id="dev" value={devName} onChange={e => setDevName(e.target.value)} /></div>
            <Button variant="primary" icon={<KeyRound className="h-4 w-4" />} onClick={pair}>Create device token</Button></div>
        )}
      </Card>

      <Card className="p-5">
        <SectionTitle><span className="flex items-center gap-2"><Link2 className="h-4 w-4" />Connected accounts</span></SectionTitle>
        <p className="mb-3 text-[13px] text-muted">{accounts.data?.access}</p>
        {(['google', 'microsoft'] as const).map(prov => {
          const a = accounts.data?.accounts.find(x => x.provider === prov)
          return (
            <div key={prov} className="flex flex-wrap items-center gap-3 border-t border-line py-3 text-sm">
              <span className="min-w-0 flex-1 font-medium">{prov === 'google' ? 'Google (Google Docs)' : 'Microsoft (Word on OneDrive / SharePoint)'}
                <span className="block text-[12px] font-normal text-muted">{a ? `Connected as ${a.account_email || 'unknown'} · read-only` : accounts.data?.configured[prov] ? 'Not connected' : 'Not configured on this server'}</span></span>
              {a ? <Button size="sm" variant="danger" onClick={async () => { await del(`/api/integrations/${prov}`); qc.invalidateQueries({ queryKey: ['accounts'] }); toast('Disconnected. Stored tokens were deleted.') }}>Disconnect</Button>
                : <Button size="sm" disabled={!accounts.data?.configured[prov]} onClick={async () => { try { window.location.href = (await get(`/api/integrations/${prov}/start`)).url } catch (e: any) { toast(e.message, 'error') } }}>Connect</Button>}
            </div>
          )
        })}
      </Card>

      <Card className="p-5">
        <SectionTitle>Personalization</SectionTitle>
        <div className="grid gap-4 md:grid-cols-3">
          <div><Label htmlFor="theme">Appearance</Label>
            <select id="theme" value={prefs.theme} onChange={e => setPref({ theme: e.target.value })} className="h-10 w-full rounded-md border border-line bg-surface px-2 text-sm">
              <option value="system">Match system</option><option value="light">Light</option><option value="dark">Dark</option></select></div>
          <div><Label htmlFor="help">AI help level</Label>
            <select id="help" value={prefs.help_level ?? 'auto'} onChange={e => setPref(e.target.value === 'auto' ? { clear_help_level: true } : { help_level: e.target.value })} className="h-10 w-full rounded-md border border-line bg-surface px-2 text-sm">
              <option value="auto">Follow my time away</option><option value="brief">Brief</option><option value="balanced">Balanced</option><option value="detailed">Detailed</option></select></div>
          <div><Label htmlFor="gap">Count as away after</Label>
            <select id="gap" value={prefs.inactivity_gap_minutes} onChange={e => setPref({ inactivity_gap_minutes: Number(e.target.value) })} className="h-10 w-full rounded-md border border-line bg-surface px-2 text-sm">
              {[2, 5, 10, 15, 30].map(m => <option key={m} value={m}>{m} minutes without activity</option>)}</select></div>
          <div className="md:col-span-2"><Check checked={prefs.break_reminders} onChange={v => setPref({ break_reminders: v })}><strong>Break reminders</strong><span className="block text-[13px] text-muted">Offer to save a checkpoint when you stop typing for a while.</span></Check></div>
          <div><Label htmlFor="brk">Remind after</Label>
            <select id="brk" value={prefs.break_threshold_minutes} disabled={!prefs.break_reminders} onChange={e => setPref({ break_threshold_minutes: Number(e.target.value) })} className="h-10 w-full rounded-md border border-line bg-surface px-2 text-sm">
              {[5, 10, 15, 20, 30, 45, 60].map(m => <option key={m} value={m}>{m} minutes</option>)}</select></div>
          <div className="md:col-span-3"><Check checked={prefs.voice_upload_allowed} onChange={v => setPref({ voice_upload_allowed: v })}><strong>Allow voice clips to be uploaded for transcription</strong>
            <span className="block text-[13px] text-muted">Only used when your browser can't transcribe speech itself. Clips go to Re-Focus AI and the configured AI service ({p.ai_provider === 'openai' ? 'OpenAI' : 'not configured on this server'}), are transcribed, and are not stored.</span></Check></div>
        </div>
      </Card>

      <Card className="p-5">
        <SectionTitle>Keyboard shortcuts</SectionTitle>
        <p className="mb-3 text-[13px] text-muted">Click a shortcut, then press the new key combination. Browser controls such as Alt+← and Ctrl+[ can't be used.</p>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(prefs.shortcuts).map(([k, v]) => (
            <div key={k} className="flex items-center justify-between gap-2 rounded-md border border-line px-3 py-2 text-sm">
              <span>{SHORTCUT_LABEL[k] ?? k}</span>
              <button onClick={() => setRecording(k)} className="rounded border border-line bg-canvas px-2 py-0.5 font-mono text-[12px]" aria-label={`Change shortcut for ${SHORTCUT_LABEL[k]}`}>{recording === k ? 'Press keys…' : v}</button>
            </div>
          ))}
        </div>
      </Card>

      <Card className="p-5">
        <SectionTitle>Your data</SectionTitle>
        <div className="flex flex-wrap gap-2"><Button icon={<Download className="h-4 w-4" />} onClick={exportData}>Export all my data (JSON)</Button></div>
        <div className="mt-5 rounded-lg border border-danger/40 p-4">
          <div className="mb-1 font-semibold text-danger">Delete account</div>
          <p className="mb-2 text-[13px]">This permanently removes your account and everything stored with it. What deletion does and doesn't cover:</p>
          <ul className="mb-3 list-disc space-y-1 pl-5 text-[13px] text-muted">{p.deletion_notes.map(n => <li key={n}>{n}</li>)}</ul>
          <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
            <Input type="password" aria-label="Password" placeholder="Your password" value={delPw} onChange={e => setDelPw(e.target.value)} />
            <Input aria-label="Type DELETE to confirm" placeholder="Type DELETE" value={delConfirm} onChange={e => setDelConfirm(e.target.value)} />
            <Button variant="danger" icon={<Trash2 className="h-4 w-4" />} disabled={delConfirm !== 'DELETE' || !delPw}
              onClick={async () => { try { await post('/api/account/delete', { password: delPw, confirm: delConfirm }); signOut() } catch (e: any) { toast(e.message, 'error') } }}>Delete account</Button>
          </div>
        </div>
      </Card>
    </div>
  )
}
