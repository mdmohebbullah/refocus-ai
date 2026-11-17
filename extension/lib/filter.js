// Local privacy filter: sensitive pages are never sent to the server at all.
// The server applies the same rules again (defence in depth).
export const ALWAYS_SKIP_SCHEMES = ['chrome:', 'chrome-extension:', 'edge:', 'about:', 'file:', 'data:', 'blob:', 'devtools:', 'view-source:'];
export const SENSITIVE_PATH = /\/(checkout|payment|billing|cart\b|login|signin|sign-in|oauth|password|account\/security|wallet)/i;

export function domainOf(url) {
  try { return new URL(url).hostname.toLowerCase().replace(/^www\./, ''); } catch { return ''; }
}

export function matchesDomain(domain, rules) {
  return rules.some(r => domain === r || domain.endsWith('.' + r));
}

/** True if this URL must not leave the browser. `exclusions` is the effective list from /api/privacy. */
export function isExcluded(url, exclusions = []) {
  if (!url) return true;
  let u;
  try { u = new URL(url); } catch { return true; }
  if (ALWAYS_SKIP_SCHEMES.includes(u.protocol) || !['http:', 'https:'].includes(u.protocol)) return true;
  const d = u.hostname.toLowerCase().replace(/^www\./, '');
  if (matchesDomain(d, exclusions)) return true;
  return SENSITIVE_PATH.test(u.pathname);
}

/** Heartbeats count only when the user is active AND looking at a tab they selected for the project. */
export function shouldHeartbeat({ idleState, activeTabUrl, selectedUrls, collectionOn, privateMode }) {
  if (idleState !== 'active' || !collectionOn || privateMode) return false;
  return !!activeTabUrl && selectedUrls.includes(activeTabUrl);
}
