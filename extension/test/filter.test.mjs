import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isExcluded, shouldHeartbeat, domainOf } from '../lib/filter.js';

const ex = ['chase.com', 'mail.google.com', 'mychart.com'];

test('browser-internal and non-http pages are never sent', () => {
  for (const u of ['chrome://settings', 'file:///Users/x/a.pdf', 'about:blank', 'chrome-extension://abc/popup.html', '', 'not a url'])
    assert.equal(isExcluded(u, ex), true, u);
});
test('excluded domains and subdomains are filtered', () => {
  assert.equal(isExcluded('https://secure.chase.com/account', ex), true);
  assert.equal(isExcluded('https://mail.google.com/mail/u/0', ex), true);
  assert.equal(isExcluded('https://docs.google.com/document/d/abc', ex), false);
});
test('checkout, payment and sign-in pages are filtered on any site', () => {
  assert.equal(isExcluded('https://shop.example.com/checkout', ex), true);
  assert.equal(isExcluded('https://example.edu/login?next=/', ex), true);
  assert.equal(isExcluded('https://scholar.google.com/scholar?q=trust', ex), false);
});
test('heartbeat only when active on a selected tab', () => {
  const base = { idleState: 'active', activeTabUrl: 'https://a.org/p', selectedUrls: ['https://a.org/p'], collectionOn: true, privateMode: false };
  assert.equal(shouldHeartbeat(base), true);
  assert.equal(shouldHeartbeat({ ...base, idleState: 'idle' }), false);
  assert.equal(shouldHeartbeat({ ...base, activeTabUrl: 'https://youtube.com' }), false);
  assert.equal(shouldHeartbeat({ ...base, privateMode: true }), false);
});
test('domainOf strips www', () => assert.equal(domainOf('https://www.Nature.com/x'), 'nature.com'));
