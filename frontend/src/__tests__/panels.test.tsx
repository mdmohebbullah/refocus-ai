/** Feature 5A — Panel Back/Forward behaves like a browser and keeps typed text. */
import { describe, expect, it } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { panelReducer, PanelProvider, usePanels, usePanelState, type PanelStackState } from '../state/panels'

describe('panelReducer', () => {
  const start: PanelStackState = { entries: [], index: -1 }
  it('opens, goes back and forward, and disables at the ends', () => {
    let s = panelReducer(start, { t: 'open', type: 'resume', props: {} })
    s = panelReducer(s, { t: 'open', type: 'why', props: { suggestionId: 1 } })
    s = panelReducer(s, { t: 'open', type: 'source', props: { url: 'x' } })
    expect(s.index).toBe(2)
    s = panelReducer(s, { t: 'back' }); s = panelReducer(s, { t: 'back' })
    expect(s.entries[s.index].type).toBe('resume')
    expect(panelReducer(s, { t: 'back' })).toBe(s) // Back disabled on first panel
    s = panelReducer(s, { t: 'forward' })
    expect(s.entries[s.index].type).toBe('why')
  })
  it('opening a new panel after going back clears Forward history', () => {
    let s = panelReducer(start, { t: 'open', type: 'resume', props: {} })
    s = panelReducer(s, { t: 'open', type: 'why', props: {} })
    s = panelReducer(s, { t: 'back' })
    s = panelReducer(s, { t: 'open', type: 'help', props: {} })
    expect(s.entries.map(e => e.type)).toEqual(['resume', 'help'])
    expect(s.index).toBe(1)
  })
  it('keeps each panel state separately', () => {
    let s = panelReducer(start, { t: 'open', type: 'review', props: {} })
    s = panelReducer(s, { t: 'setState', key: s.entries[0].key, field: 'text', value: 'my step' })
    s = panelReducer(s, { t: 'open', type: 'why', props: {} })
    s = panelReducer(s, { t: 'back' })
    expect(s.entries[s.index].state.text).toBe('my step')
  })
})

function Harness() {
  const p = usePanels()
  const [text, setText] = usePanelState('text', '')
  return (
    <div>
      <button onClick={() => p.open('review', {})}>open review</button>
      <button onClick={() => p.open('why', {})}>open why</button>
      <button onClick={p.back} disabled={!p.canBack}>back</button>
      <button onClick={p.forward} disabled={!p.canForward}>forward</button>
      <span data-testid="type">{p.current?.type ?? 'none'}</span>
      {p.current?.type === 'review' && <input aria-label="step" value={text} onChange={e => setText(e.target.value)} />}
    </div>
  )
}

describe('usePanelState', () => {
  it('restores typed text after Back/Forward', () => {
    render(<PanelProvider><Harness /></PanelProvider>)
    act(() => { fireEvent.click(screen.getByText('open review')) })
    fireEvent.change(screen.getByLabelText('step'), { target: { value: 'Check the discussion first' } })
    act(() => { fireEvent.click(screen.getByText('open why')) })
    expect(screen.getByTestId('type').textContent).toBe('why')
    act(() => { fireEvent.click(screen.getByText('back')) })
    expect((screen.getByLabelText('step') as HTMLInputElement).value).toBe('Check the discussion first')
    expect((screen.getByText('forward') as HTMLButtonElement).disabled).toBe(false)
  })
})
