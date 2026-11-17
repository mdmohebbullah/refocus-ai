const TOKEN_KEY = 'refocus.token'

export const API_BASE: string = (import.meta as any).env?.VITE_API_URL ?? ''

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}
export function setToken(t: string | null) {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch { /* storage unavailable */ }
}

export class ApiError extends Error {
  status: number
  detail: any
  constructor(status: number, detail: any) {
    super(typeof detail === 'string' ? detail : detail?.message ?? JSON.stringify(detail))
    this.status = status
    this.detail = detail
  }
}

export async function api<T = any>(path: string, opts: { method?: string; body?: any; form?: FormData } = {}): Promise<T> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let body: BodyInit | undefined
  if (opts.form) body = opts.form
  else if (opts.body !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(opts.body) }
  const res = await fetch(API_BASE + path, { method: opts.method ?? (body ? 'POST' : 'GET'), headers, body })
  if (res.status === 204) return undefined as T
  const text = await res.text()
  const data = text ? (() => { try { return JSON.parse(text) } catch { return text } })() : undefined
  if (!res.ok) {
    if (res.status === 401 && token) { setToken(null); window.dispatchEvent(new Event('refocus:signed-out')) }
    const detail = data?.detail ?? data ?? res.statusText
    throw new ApiError(res.status, Array.isArray(detail) ? detail.map((d: any) => d.msg).join('; ') : detail)
  }
  return data as T
}

export const get = <T = any>(p: string) => api<T>(p)
export const post = <T = any>(p: string, body?: any) => api<T>(p, { method: 'POST', body: body ?? {} })
export const patch = <T = any>(p: string, body: any) => api<T>(p, { method: 'PATCH', body })
export const put = <T = any>(p: string, body: any) => api<T>(p, { method: 'PUT', body })
export const del = <T = any>(p: string) => api<T>(p, { method: 'DELETE' })
