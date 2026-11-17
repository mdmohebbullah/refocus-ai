import { call, DEFAULTS, save, settings } from '../lib/api.js';
import { isExcluded } from '../lib/filter.js';

const $ = id => document.getElementById(id);
const msg = t => { $('msg').textContent = t; setTimeout(() => { $('msg').textContent = ''; }, 4000); };

async function init() {
  const s = await settings();
  $('apiBase').value = s.apiBase; $('appUrl').value = s.appUrl;
  if (!s.token) return showPair();
  try {
    const me = await call('/api/me');
    if (!me.device) throw new Error('This token is not a device token');
    await chrome.runtime.sendMessage({ type: 'sync-now' });
    showMain(me, await settings());
  } catch (e) { showPair(e.message); }
}

function showPair(err = '') {
  $('pair').hidden = false; $('main').hidden = true;
  $('status').textContent = 'Not paired'; $('status').className = 'pill';
  $('pairErr').textContent = err;
}

async function showMain(me, s) {
  $('pair').hidden = true; $('main').hidden = false;
  $('status').textContent = s.privateMode ? 'Private mode' : (s.collectionOn ? 'Connected' : 'Collection off');
  $('status').className = 'pill' + (s.collectionOn && !s.privateMode ? ' ok' : '');
  const { projects } = await call('/api/projects');
  const pid = s.projectId ?? me.preferences.current_project_id ?? projects[0]?.id ?? null;
  await save({ projectId: pid });
  $('project').innerHTML = projects.map(p => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');
  $('project').value = pid ?? '';
  $('collect').checked = !!me.device.collection_enabled;
  $('history').checked = s.historyEnabled && await chrome.permissions.contains({ permissions: ['history'] });
  $('content').checked = !!me.device.content_access;
  $('private').checked = s.privateMode;
  await renderTabs(); await renderActivity();
}

const escapeHtml = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

async function renderTabs() {
  const s = await settings();
  const { tabs } = await call('/api/tabs');
  const mine = tabs.filter(t => !t.excluded);
  $('tabCount').textContent = `(${mine.filter(t => t.selected).length} selected)`;
  $('tabs').innerHTML = mine.length ? mine.map(t => `<li><input type="checkbox" data-id="${t.id}" ${t.selected ? 'checked' : ''} aria-label="Use ${escapeHtml(t.title)}">
    ${t.fav_icon_url ? `<img src="${escapeHtml(t.fav_icon_url)}" alt="">` : ''}<span class="t" title="${escapeHtml(t.url)}">${escapeHtml(t.title)}</span></li>`).join('')
    : '<li class="muted">No tabs yet.</li>';
  $('tabs').querySelectorAll('input').forEach(cb => cb.addEventListener('change', async () => {
    await call('/api/tabs/select', { method: 'POST', body: { tab_ids: [Number(cb.dataset.id)], selected: cb.checked, project_id: cb.checked ? s.projectId : null } });
    renderTabs();
  }));
}

async function renderActivity() {
  try {
    const { events } = await call('/api/activity?minutes=60');
    $('activity').innerHTML = events.slice(0, 8).map(e => `<li><span class="t">${escapeHtml(e.excluded ? 'Excluded website' : e.title)}</span><span class="muted tiny">${new Date(e.occurred_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</span></li>`).join('') || '<li class="muted">Nothing recorded.</li>';
  } catch { /* ignore */ }
}

$('pairBtn').addEventListener('click', async () => {
  const apiBase = $('apiBase').value.trim() || DEFAULTS.apiBase, appUrl = $('appUrl').value.trim() || DEFAULTS.appUrl, token = $('token').value.trim();
  if (!token.startsWith('rfd_')) { $('pairErr').textContent = 'Paste the device token from Settings (it starts with rfd_).'; return; }
  await save({ apiBase, appUrl, token });
  await chrome.runtime.sendMessage({ type: 'setup' });
  init();
});
$('project').addEventListener('change', async e => { await save({ projectId: Number(e.target.value) }); await call('/api/me/preferences', { method: 'PATCH', body: { current_project_id: Number(e.target.value) } }); });
$('pauseBtn').addEventListener('click', async () => { const s = await settings(); chrome.tabs.create({ url: `${s.appUrl}/?pause=1` }); });
$('openBtn').addEventListener('click', async () => { const s = await settings(); chrome.tabs.create({ url: s.appUrl }); });
async function setAll(selected) {
  const s = await settings(); const { tabs } = await call('/api/tabs');
  await call('/api/tabs/select', { method: 'POST', body: { tab_ids: tabs.filter(t => !t.excluded).map(t => t.id), selected, project_id: selected ? s.projectId : null } });
  renderTabs();
}
$('selAll').addEventListener('click', () => setAll(true));
$('selNone').addEventListener('click', () => setAll(false));
$('saveThought').addEventListener('click', async () => {
  const s = await settings(); const text = $('thought').value;
  if (!text.trim() || !s.projectId) return;
  await call('/api/thoughts', { method: 'POST', body: { project_id: s.projectId, thinking: text, origin: 'quick' } });
  $('thought').value = ''; msg('Thought saved as your own note.');
});
$('saveSource').addEventListener('click', async () => {
  const s = await settings();
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || isExcluded(tab.url, s.exclusions)) { msg('This page is excluded for privacy and cannot be saved.'); return; }
  await call('/api/references', { method: 'POST', body: { project_id: s.projectId, title: tab.title || tab.url, url: tab.url, why_saved: $('why').value } });
  $('why').value = ''; msg('Source saved.');
});
$('collect').addEventListener('change', async e => {
  const s = await settings(); await call(`/api/devices/${s.deviceId}`, { method: 'PATCH', body: { collection_enabled: e.target.checked } });
  await chrome.runtime.sendMessage({ type: 'sync-now' }); init();
});
$('history').addEventListener('change', async e => {
  if (e.target.checked) {
    const ok = await chrome.permissions.request({ permissions: ['history'] });
    e.target.checked = ok; await save({ historyEnabled: ok });
  } else { await chrome.permissions.remove({ permissions: ['history'] }); await save({ historyEnabled: false }); }
  await chrome.runtime.sendMessage({ type: 'sync-now' }); renderActivity();
});
$('content').addEventListener('change', async e => {
  const s = await settings();
  let ok = false;
  if (e.target.checked) ok = await chrome.permissions.request({ permissions: ['scripting'], origins: ['https://*/*', 'http://*/*'] });
  else await chrome.permissions.remove({ permissions: ['scripting'], origins: ['https://*/*', 'http://*/*'] });
  e.target.checked = ok;
  await call(`/api/devices/${s.deviceId}`, { method: 'PATCH', body: { content_access: ok } });
  await chrome.runtime.sendMessage({ type: 'sync-now' });
});
$('private').addEventListener('change', async e => { await call('/api/privacy', { method: 'PATCH', body: { private_mode: e.target.checked } }); await chrome.runtime.sendMessage({ type: 'sync-now' }); init(); });
$('unpair').addEventListener('click', async () => { await save({ token: '', deviceId: null }); showPair(); });

init();
