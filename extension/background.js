// Re-Focus AI service worker (Manifest V3).
// Survives restarts: every value is in chrome.storage and work is driven by chrome.alarms.
import { call, save, settings } from './lib/api.js';
import { domainOf, isExcluded, shouldHeartbeat } from './lib/filter.js';

const SYNC_ALARM = 'refocus-sync';
const HISTORY_ALARM = 'refocus-history';
const BEAT_ALARM = 'refocus-heartbeat';

async function setupAlarms() {
  const s = await settings();
  await chrome.alarms.create(SYNC_ALARM, { periodInMinutes: 1 });
  await chrome.alarms.create(HISTORY_ALARM, { periodInMinutes: 5 });
  await chrome.alarms.create(BEAT_ALARM, { periodInMinutes: 1 });
  chrome.idle.setDetectionInterval(Math.max(60, (s.breakMinutes || 10) * 60));
}
chrome.runtime.onInstalled.addListener(setupAlarms);
chrome.runtime.onStartup.addListener(setupAlarms);

/** Pull privacy settings so sensitive URLs are filtered before anything leaves the browser. */
export async function refreshPolicy() {
  try {
    const [p, me] = await Promise.all([call('/api/privacy'), call('/api/me')]);
    await save({ exclusions: p.effective_exclusions, privateMode: p.private_mode, collectionOn: p.activity_collection && (me.device?.collection_enabled ?? true),
      deviceId: me.device?.id ?? null, breakReminders: me.preferences.break_reminders, breakMinutes: me.preferences.break_threshold_minutes,
      contentEnabled: !!me.device?.content_access, lastError: '' });
  } catch (e) { await save({ lastError: String(e.message || e) }); }
}

async function hasPermission(perm) { return chrome.permissions.contains({ permissions: [perm] }); }

async function pageInfo(tabId) {
  // Only with explicit content permission: reads a short excerpt and whether the page has a password field.
  try {
    const [r] = await chrome.scripting.executeScript({ target: { tabId }, func: () => ({
      hasPassword: !!document.querySelector('input[type=password]'),
      excerpt: (document.querySelector('main, article') || document.body)?.innerText?.slice(0, 2000) || '' }) });
    return r?.result || null;
  } catch { return null; }
}

export async function syncTabs() {
  const s = await settings();
  if (!s.token) return;
  await refreshPolicy();
  const fresh = await settings();
  if (fresh.privateMode || !fresh.collectionOn) { await call('/api/tabs/sync', { method: 'POST', body: { tabs: [] } }).catch(() => {}); return; }
  const tabs = await chrome.tabs.query({});
  const canRead = fresh.contentEnabled && await hasPermission('scripting');
  let selected = [];
  if (canRead) { try { selected = (await call('/api/tabs')).tabs.filter(t => t.selected).map(t => t.url); } catch { /* ignore */ } }
  const out = [];
  for (const t of tabs) {
    if (isExcluded(t.url, fresh.exclusions)) continue;   // never sent
    const item = { tab_id: t.id, window_id: t.windowId, title: t.title || '', url: t.url, fav_icon_url: t.favIconUrl || null, status: t.status || 'complete' };
    if (canRead && selected.includes(t.url)) {
      const info = await pageInfo(t.id);
      if (info?.hasPassword) continue;                     // pages with a password field are never sent
      if (info) item.content_excerpt = info.excerpt;
    }
    out.push(item);
  }
  await call('/api/tabs/sync', { method: 'POST', body: { tabs: out } }).catch(e => save({ lastError: e.message }));
}

export async function syncHistory() {
  const s = await settings();
  if (!s.token || !s.historyEnabled || s.privateMode || !s.collectionOn || !(await hasPermission('history'))) return;
  const items = await chrome.history.search({ text: '', startTime: Date.now() - 60 * 60 * 1000, maxResults: 300 });
  const events = items.filter(i => !isExcluded(i.url, s.exclusions) && i.lastVisitTime)
    .map(i => ({ title: i.title || domainOf(i.url), url: i.url, occurred_at: new Date(i.lastVisitTime).toISOString(), project_id: s.projectId }));
  if (events.length) await call('/api/activity/batch', { method: 'POST', body: { events } }).catch(e => save({ lastError: e.message }));
}

async function heartbeat() {
  const s = await settings();
  if (!s.token || !s.projectId) return;
  const idleState = await chrome.idle.queryState(60);
  const [active] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  let selectedUrls = [];
  try { selectedUrls = (await call('/api/tabs')).tabs.filter(t => t.selected && t.project_id === s.projectId).map(t => t.url); } catch { return; }
  if (shouldHeartbeat({ idleState, activeTabUrl: active?.url, selectedUrls, collectionOn: s.collectionOn, privateMode: s.privateMode })) {
    await call('/api/time/heartbeat', { method: 'POST', body: { project_id: s.projectId, source: 'extension' } }).catch(() => {});
  }
}

let syncTimer = null;
function scheduleSync() { clearTimeout(syncTimer); syncTimer = setTimeout(syncTabs, 1500); }
chrome.tabs.onUpdated.addListener((_, info) => { if (info.status === 'complete' || info.title) scheduleSync(); });
chrome.tabs.onRemoved.addListener(scheduleSync);
chrome.tabs.onCreated.addListener(scheduleSync);

chrome.alarms.onAlarm.addListener(a => {
  if (a.name === SYNC_ALARM) syncTabs();
  if (a.name === HISTORY_ALARM) syncHistory();
  if (a.name === BEAT_ALARM) heartbeat();
});

// Smart break detection (Feature 17): unobtrusive, can be turned off in Settings.
chrome.idle.onStateChanged.addListener(async state => {
  const s = await settings();
  if (state !== 'idle' || !s.token || !s.breakReminders || !s.projectId) return;
  chrome.notifications.create('refocus-break', {
    type: 'basic', iconUrl: 'icons/128.png', title: 'Taking a break?',
    message: 'Would you like to save your current progress before leaving?',
    buttons: [{ title: 'Save checkpoint' }, { title: 'Dismiss' }], priority: 0,
  });
});
chrome.notifications.onButtonClicked.addListener(async (id, i) => {
  if (id !== 'refocus-break') return;
  chrome.notifications.clear(id);
  if (i === 0) { const s = await settings(); chrome.tabs.create({ url: `${s.appUrl}/?pause=1` }); }
});

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  (async () => {
    if (msg.type === 'sync-now') { await syncTabs(); await syncHistory(); }
    if (msg.type === 'setup') await setupAlarms();
    reply({ ok: true });
  })();
  return true;
});
