/**
 * Feature 18 — Voice Thought Capture.
 * - Explicit Start / Stop; never records continuously (auto-stops after 60 s).
 * - Uses the browser's speech recognition when available. In Chrome this sends audio to the
 *   browser vendor's speech service, so the user is told that before the first use.
 * - Otherwise, if the user allowed audio upload in Settings and the server has AI configured,
 *   the clip is uploaded to Re-Focus AI for transcription.
 * - Otherwise the button explains that typing is the fallback.
 * The transcript is inserted into the text field, where it stays editable.
 */
import { useEffect, useRef, useState } from 'react'
import { Mic, Square } from 'lucide-react'
import { api } from '../api/client'
import { useApp } from '../state/app'
import { cx } from './ui'

const CONSENT_KEY = 'refocus.voiceConsent'
const MAX_MS = 60_000

function speechCtor(): any { return (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition || null }

export function VoiceButton({ onText, projectId }: { onText: (t: string) => void; projectId?: number }) {
  const { me, toast } = useApp()
  const [state, setState] = useState<'idle' | 'consent' | 'recording' | 'transcribing'>('idle')
  const rec = useRef<any>(null)
  const timer = useRef<number | null>(null)
  const Speech = speechCtor()
  const canUpload = !!me?.preferences.voice_upload_allowed && typeof MediaRecorder !== 'undefined' && !!navigator.mediaDevices
  const mode: 'speech' | 'upload' | 'none' = Speech ? 'speech' : canUpload ? 'upload' : 'none'

  useEffect(() => () => { stop() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  function stop() {
    if (timer.current) { clearTimeout(timer.current); timer.current = null }
    try { rec.current?.stop() } catch { /* already stopped */ }
  }

  async function start() {
    if (mode === 'speech') {
      const r = new Speech()
      r.lang = navigator.language || 'en-US'
      r.interimResults = false
      r.continuous = false
      r.onresult = (e: any) => { const t = Array.from(e.results).map((x: any) => x[0].transcript).join(' ').trim(); if (t) onText(t) }
      r.onerror = (e: any) => { toast(e.error === 'not-allowed' ? 'Microphone permission was denied. You can type instead.' : 'Voice capture failed. You can type instead.', 'error') }
      r.onend = () => setState('idle')
      rec.current = r
      r.start()
      setState('recording')
    } else if (mode === 'upload') {
      let stream: MediaStream
      try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }) } catch {
        toast('Microphone permission was denied. You can type instead.', 'error'); setState('idle'); return
      }
      const chunks: Blob[] = []
      const mr = new MediaRecorder(stream)
      mr.ondataavailable = e => chunks.push(e.data)
      mr.onstop = async () => {
        stream.getTracks().forEach(t => t.stop())
        setState('transcribing')
        try {
          const form = new FormData()
          form.append('audio', new Blob(chunks, { type: mr.mimeType || 'audio/webm' }), 'thought.webm')
          if (projectId) form.append('project_id', String(projectId))
          const r = await api<{ text: string }>('/api/voice/transcribe', { method: 'POST', form })
          if (r.text) onText(r.text)
        } catch (e: any) { toast(e.message || 'Transcription is unavailable. Please type instead.', 'error') }
        setState('idle')
      }
      rec.current = mr
      mr.start()
      setState('recording')
    }
    timer.current = window.setTimeout(stop, MAX_MS)
  }

  const click = () => {
    if (mode === 'none') { toast('Voice input is not available in this browser. Please type your thought.', 'info'); return }
    if (state === 'recording') { stop(); return }
    let ok = false
    try { ok = localStorage.getItem(CONSENT_KEY) === mode } catch { /* ignore */ }
    if (!ok) { setState('consent'); return }
    start()
  }

  return (
    <div className="relative shrink-0">
      <button type="button" onClick={click} disabled={state === 'transcribing'}
        aria-label={state === 'recording' ? 'Stop recording' : 'Start voice capture'} aria-pressed={state === 'recording'}
        title={mode === 'none' ? 'Voice input unavailable here — please type' : state === 'recording' ? 'Stop' : 'Speak your thought'}
        className={cx('flex h-10 w-10 items-center justify-center rounded-md border',
          state === 'recording' ? 'border-danger bg-danger-bg text-danger' : 'border-line bg-surface text-ink hover:bg-canvas', mode === 'none' && 'opacity-50')}>
        {state === 'recording' ? <Square className="h-4 w-4 fill-current" /> : <Mic className="h-4 w-4" />}
      </button>
      {state === 'recording' && <span className="absolute -bottom-5 right-0 whitespace-nowrap text-[11px] font-semibold text-danger">● Recording</span>}
      {state === 'transcribing' && <span className="absolute -bottom-5 right-0 whitespace-nowrap text-[11px] text-muted">Transcribing…</span>}
      {state === 'consent' && (
        <div role="dialog" aria-label="Voice capture permission" className="absolute right-0 top-11 z-20 w-72 rounded-lg border border-line bg-surface p-3 text-[13px] shadow-xl">
          <p className="mb-2 font-semibold">Use your microphone?</p>
          <p className="mb-3 text-muted">
            {mode === 'speech'
              ? 'Your browser turns speech into text. In Chrome and Edge, the audio is sent to the browser company’s speech service. Recording stops when you press Stop or after 60 seconds.'
              : 'Your clip is uploaded to Re-Focus AI and transcribed by the configured AI service, then the audio is discarded. Recording stops when you press Stop or after 60 seconds.'}
          </p>
          <div className="flex justify-end gap-2">
            <button className="rounded-md px-3 py-1.5 hover:bg-canvas" onClick={() => setState('idle')}>Cancel</button>
            <button className="rounded-md bg-navy px-3 py-1.5 font-semibold text-[rgb(var(--on-navy))]"
              onClick={() => { try { localStorage.setItem(CONSENT_KEY, mode) } catch { /* ignore */ } setState('idle'); start() }}>Allow and start</button>
          </div>
        </div>
      )}
    </div>
  )
}
