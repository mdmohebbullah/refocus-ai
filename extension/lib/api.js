// Small client for the Re-Focus AI API. All state lives in chrome.storage so the
// service worker can be stopped and restarted at any time.
export const DEFAULTS = { apiBase: 'http://localhost:8000', appUrl: 'http://localhost:5173', token: '', projectId: null,
  historyEnabled: false, contentEnabled: false, exclusions: [], privateMode: false, collectionOn: true, breakReminders: true,
  breakMinutes: 10, deviceId: null, lastError: '' };

export async function settings() {
  const s = await chrome.storage.local.get(Object.keys(DEFAULTS));
  return { ...DEFAULTS, ...s };
}
export async function save(patch) { await chrome.storage.local.set(patch); }

export async function call(path, { method = 'GET', body } = {}) {
  const s = await settings();
  if (!s.token) throw new Error('Not paired');
  const res = await fetch(s.apiBase.replace(/\/$/, '') + path, {
    method, headers: { Authorization: `Bearer ${s.token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${res.status})`);
  return data;
}
