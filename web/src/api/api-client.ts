// Error that carries HTTP status + backend error code so callers can branch
// without string-matching. Backend envelope: { error: { code, message } }.
export class ApiError extends Error {
  status: number
  code: string | null
  constructor(message: string, status: number, code: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

// Pull { error: { code, message } } from a failed response; fall back to text
// then to statusText so the thrown ApiError always carries something readable.
async function toApiError(res: Response): Promise<ApiError> {
  try {
    const body = (await res.clone().json()) as
      | { error?: { code?: string; message?: string }; detail?: unknown }
      | undefined
    const err = body?.error
    if (err?.message) return new ApiError(err.message, res.status, err.code ?? null)
    if (typeof body?.detail === 'string') return new ApiError(body.detail, res.status)
  } catch {
    try {
      const text = await res.text()
      if (text) return new ApiError(text.slice(0, 300), res.status)
    } catch {
      // ignore — fall through to statusText
    }
  }
  return new ApiError(res.statusText || `API ${res.status}`, res.status)
}

const TOKEN_KEY = 'pq.adminToken'

// Set when the owner dismisses the prompt on a read; reset only by a page reload.
let readPromptDeclined = false

// Mutations and the guarded reads carry X-Admin-Token from localStorage. The token
// is never baked in at build time: a VITE_* value would ship in the bundle. A 401
// retries once: silently when another request stored a newer token meanwhile,
// otherwise after one prompt. A declined prompt is not repeated by polled reads.
async function send(path: string, init: RequestInit, read = false): Promise<Response> {
  const attempt = (token: string | null) => {
    const headers = new Headers(init.headers)
    if (token) headers.set('X-Admin-Token', token)
    return fetch(new URL(path, window.location.origin), { ...init, headers })
  }
  const sent = localStorage.getItem(TOKEN_KEY)
  let res = await attempt(sent)
  if (res.status === 401) {
    const stored = localStorage.getItem(TOKEN_KEY)
    if (stored && stored !== sent) {
      res = await attempt(stored)
    } else if (!(read && readPromptDeclined)) {
      const answer = window.prompt('Admin token')
      if (answer) {
        localStorage.setItem(TOKEN_KEY, answer)
        res = await attempt(answer)
      } else if (read) {
        readPromptDeclined = true
      }
    }
  }
  if (!res.ok) throw await toApiError(res)
  return res
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await send(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return res.json()
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const res = await send(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return res.json()
}

export async function apiDelete(path: string): Promise<void> {
  await send(path, { method: 'DELETE' })
}

function buildUrl(path: string, params?: Record<string, string>): string {
  const url = new URL(path, window.location.origin)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== '') url.searchParams.set(k, v)
    }
  }
  return url.toString()
}

export async function apiFetch<T>(path: string, params?: Record<string, string>): Promise<T> {
  const res = await fetch(buildUrl(path, params))
  if (!res.ok) throw await toApiError(res)
  return res.json()
}

export async function apiFetchAdmin<T>(path: string, params?: Record<string, string>): Promise<T> {
  const res = await send(buildUrl(path, params), { method: 'GET' }, true)
  return res.json()
}
