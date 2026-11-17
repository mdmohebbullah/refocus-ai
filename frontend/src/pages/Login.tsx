import { useState } from 'react'
import { useApp } from '../state/app'
import { Button, Input, Label } from '../components/ui'

export function LoginPage() {
  const { signIn, register } = useApp()
  const [mode, setMode] = useState<'in' | 'up'>('in')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(''); setBusy(true)
    try { mode === 'in' ? await signIn(email, password) : await register(name, email, password) }
    catch (x: any) { setErr(x.message) } finally { setBusy(false) }
  }
  return (
    <div className="flex min-h-full items-center justify-center p-6">
      <div className="grid w-full max-w-[920px] overflow-hidden rounded-xl border border-line bg-surface md:grid-cols-2">
        <div className="bg-navy p-8 text-[rgb(var(--on-navy))]">
          <img src="/favicon.svg" alt="" className="mb-6 h-10 w-10 rounded-lg ring-2 ring-white/30" />
          <h1 className="font-hand text-[52px] font-bold leading-none">Re-Focus AI</h1>
          <p className="mt-1 text-[17px] opacity-90">Pick up where you left off.</p>
          <ol className="mt-10 space-y-5 text-[14px]">
            <li><strong className="block text-[15px]">What was I trying to do?</strong><span className="opacity-80">Your saved goal and unfinished thought.</span></li>
            <li><strong className="block text-[15px]">Where did I stop?</strong><span className="opacity-80">The exact sentence, highlighted.</span></li>
            <li><strong className="block text-[15px]">What should I do now?</strong><span className="opacity-80">One next step you approve.</span></li>
          </ol>
        </div>
        <form onSubmit={submit} className="space-y-4 p-8">
          <h2 className="text-xl font-semibold">{mode === 'in' ? 'Sign in' : 'Create your account'}</h2>
          {mode === 'up' && <div><Label htmlFor="name">Name</Label><Input id="name" value={name} onChange={e => setName(e.target.value)} required autoComplete="name" /></div>}
          <div><Label htmlFor="email">Email</Label><Input id="email" type="email" value={email} onChange={e => setEmail(e.target.value)} required autoComplete="email" /></div>
          <div><Label htmlFor="password" hint={mode === 'up' ? '(at least 8 characters)' : undefined}>Password</Label>
            <Input id="password" type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={mode === 'up' ? 8 : 1} autoComplete={mode === 'in' ? 'current-password' : 'new-password'} /></div>
          {err && <p role="alert" className="text-sm text-danger">{err}</p>}
          <Button variant="primary" size="lg" className="w-full" loading={busy} type="submit">{mode === 'in' ? 'Sign in' : 'Create account'}</Button>
          <p className="text-center text-sm text-muted">
            {mode === 'in' ? 'New here?' : 'Already have an account?'}{' '}
            <button type="button" className="font-semibold text-fact underline" onClick={() => setMode(mode === 'in' ? 'up' : 'in')}>{mode === 'in' ? 'Create an account' : 'Sign in'}</button>
          </p>
        </form>
      </div>
    </div>
  )
}
