/** Tracks real user input (keyboard, pointer, scroll) — background tabs never count as activity. */
let lastInput = Date.now()
const listeners = new Set<() => void>()
const mark = () => { const wasIdle = Date.now() - lastInput > 60_000; lastInput = Date.now(); if (wasIdle) listeners.forEach(l => l()) }
if (typeof window !== 'undefined') {
  for (const ev of ['keydown', 'pointerdown', 'pointermove', 'wheel', 'touchstart']) window.addEventListener(ev, mark, { passive: true })
}
export const lastInputAt = () => lastInput
export const onActive = (fn: () => void) => { listeners.add(fn); return () => { listeners.delete(fn) } }
export const isEngaged = () => document.visibilityState === 'visible' && document.hasFocus() && Date.now() - lastInput < 60_000
