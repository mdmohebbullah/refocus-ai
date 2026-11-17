import { forwardRef, type ButtonHTMLAttributes, type ReactNode, type InputHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import { Activity, BookmarkCheck, CircleCheck, Lightbulb, Loader2, Sparkles } from 'lucide-react'
import type { Provenance } from '../api/types'

export function cx(...c: (string | false | null | undefined)[]) { return c.filter(Boolean).join(' ') }

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'selected'
export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: 'sm' | 'md' | 'lg'; loading?: boolean; icon?: ReactNode }>(
  function Button({ variant = 'secondary', size = 'md', loading, icon, className, children, disabled, ...rest }, ref) {
    const v = {
      primary: 'bg-navy text-[rgb(var(--on-navy))] border-ink sketch-sm hover:opacity-90',
      secondary: 'bg-surface text-ink border-ink/60 hover:bg-canvas',
      ghost: 'bg-transparent text-ink border-transparent hover:bg-canvas',
      danger: 'bg-surface text-danger border-danger/40 hover:bg-danger-bg',
      selected: 'bg-fact-bg text-fact border-fact border-[1.5px]',
    }[variant]
    const s = { sm: 'h-8 px-3 text-[14px]', md: 'h-10 px-4 text-[16px]', lg: 'h-12 px-5 text-[17px]' }[size]
    return (
      <button ref={ref} disabled={disabled || loading}
        className={cx('inline-flex items-center justify-center gap-2 rounded-md border-2 font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed', v, s, className)}
        {...rest}>
        {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : icon}
        {children}
      </button>
    )
  })

export function Card({ children, className, ...rest }: { children: ReactNode; className?: string } & React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cx('rounded-lg border-2 border-ink/70 bg-surface sketch', className)} {...rest}>{children}</div>
}

export function SectionTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return <div className="mb-3 flex items-center justify-between gap-3"><h2 className="font-hand text-[26px] font-bold leading-none">{children}</h2>{action}</div>
}

const PROV: Record<Provenance, { label: string; icon: any; cls: string }> = {
  saved_by_you: { label: 'Saved by You', icon: BookmarkCheck, cls: 'text-fact bg-fact-bg border-fact/30' },
  recorded_activity: { label: 'Recorded Activity', icon: Activity, cls: 'text-muted bg-canvas border-line' },
  ai_guess: { label: 'AI Guess', icon: Sparkles, cls: 'text-guess bg-guess-bg border-guess/40 border-dashed' },
  ai_suggestion: { label: 'AI Suggestion', icon: Lightbulb, cls: 'text-guess bg-guess-bg border-guess/40 border-dashed' },
  user_confirmed: { label: 'User Confirmed', icon: CircleCheck, cls: 'text-ok bg-ok-bg border-ok/30' },
}

/** Provenance label: icon + text, never colour alone. */
export function ProvBadge({ kind, extra }: { kind: Provenance; extra?: string }) {
  const p = PROV[kind]
  const Icon = p.icon
  return (
    <span className={cx('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold', p.cls)}>
      <Icon className="h-3 w-3" aria-hidden />{p.label}{extra ? <span className="font-normal opacity-80">· {extra}</span> : null}
    </span>
  )
}

/** A box whose border style encodes provenance: solid = fact, dashed = AI. */
export function ProvBox({ kind, title, children, className, right }: { kind: Provenance; title?: ReactNode; children: ReactNode; className?: string; right?: ReactNode }) {
  const style = {
    saved_by_you: 'border-fact/50 bg-fact-bg/60',
    recorded_activity: 'border-line bg-canvas',
    ai_guess: 'border-guess/60 border-dashed bg-guess-bg/70',
    ai_suggestion: 'border-guess/60 border-dashed bg-guess-bg/70',
    user_confirmed: 'border-ok/50 bg-ok-bg/70',
  }[kind]
  return (
    <div className={cx('rounded-lg border-2 p-3.5', style, className)}>
      <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          {title && <span className="text-[13px] font-semibold text-ink">{title}</span>}
          <ProvBadge kind={kind} />
        </div>
        {right}
      </div>
      <div className="text-[14px] leading-relaxed text-ink">{children}</div>
    </div>
  )
}

export function Label({ htmlFor, children, hint }: { htmlFor?: string; children: ReactNode; hint?: ReactNode }) {
  return <label htmlFor={htmlFor} className="mb-1 block text-[13px] font-semibold text-ink">{children}{hint && <span className="ml-1 font-normal text-muted">{hint}</span>}</label>
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...rest }, ref) {
  return <input ref={ref} className={cx('h-10 w-full rounded-md border-[1.5px] border-ink/40 bg-surface px-3 text-sm text-ink placeholder:text-excl', className)} {...rest} />
})
export const TextArea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function TextArea({ className, ...rest }, ref) {
  return <textarea ref={ref} className={cx('w-full resize-y rounded-md border-[1.5px] border-ink/40 bg-surface px-3 py-2 text-sm leading-relaxed text-ink placeholder:text-excl', className)} {...rest} />
})

export function Check({ checked, onChange, children, disabled, id }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode; disabled?: boolean; id?: string }) {
  return (
    <label className={cx('flex min-h-[34px] cursor-pointer items-start gap-2.5 py-1 text-sm', !checked && 'text-muted', disabled && 'opacity-50')}>
      <input id={id} type="checkbox" className="mt-0.5 h-4 w-4 shrink-0 accent-[rgb(var(--navy))]" checked={checked} disabled={disabled} onChange={e => onChange(e.target.checked)} />
      <span className="min-w-0 flex-1">{children}</span>
    </label>
  )
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return <div className="flex items-center gap-2 p-6 text-sm text-muted" role="status"><Loader2 className="h-4 w-4 animate-spin" aria-hidden />{label}…</div>
}

export function Empty({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-line px-6 py-10 text-center">
      {icon && <div className="text-excl">{icon}</div>}
      <div className="font-semibold">{title}</div>
      {children && <div className="max-w-md text-sm text-muted">{children}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

export function Pill({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'blue' | 'green' | 'amber' | 'red' | 'gray' }) {
  const t = { neutral: 'bg-canvas text-ink border-line', blue: 'bg-fact-bg text-fact border-fact/30', green: 'bg-ok-bg text-ok border-ok/30',
    amber: 'bg-guess-bg text-guess border-guess/30', red: 'bg-danger-bg text-danger border-danger/30', gray: 'bg-canvas text-excl border-line' }[tone]
  return <span className={cx('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[12px] font-medium', t)}>{children}</span>
}

export function PageHeader({ title, sub, actions }: { title: string; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div><h1 className="font-hand text-[40px] font-bold leading-none">{title}</h1>{sub && <p className="mt-1 text-sm text-muted">{sub}</p>}</div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function fmtDuration(seconds: number): string {
  if (!seconds || seconds < 60) return `${Math.max(0, Math.round(seconds || 0))} s`
  const m = Math.round(seconds / 60)
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60), r = m % 60
  return r ? `${h} h ${r} min` : `${h} h`
}
export function fmtMinutes(min: number | null | undefined): string {
  if (min === null || min === undefined) return 'Not recorded yet'
  return fmtDuration(min * 60)
}
export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}
export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return 'never'
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return `${Math.round(s / 86400)} d ago`
}
export function shortUrl(url: string | null | undefined): string {
  if (!url) return ''
  try { const u = new URL(url); return u.hostname.replace(/^www\./, '') + (u.pathname.length > 1 ? u.pathname.slice(0, 28) + (u.pathname.length > 28 ? '…' : '') : '') } catch { return url }
}
