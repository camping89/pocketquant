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

// Mutations carry X-Admin-Token from localStorage. The token is never baked in
// at build time: a VITE_* value would ship in the bundle. A 401 prompts once,
// stores the answer and retries once.
async function send(path: string, init: RequestInit): Promise<Response> {
  const attempt = () => {
    const headers = new Headers(init.headers)
    const token = localStorage.getItem(TOKEN_KEY)
    if (token) headers.set('X-Admin-Token', token)
    return fetch(new URL(path, window.location.origin), { ...init, headers })
  }
  let res = await attempt()
  if (res.status === 401) {
    const answer = window.prompt('Admin token')
    if (answer) {
      localStorage.setItem(TOKEN_KEY, answer)
      res = await attempt()
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

export async function apiFetch<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(path, window.location.origin)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== '') url.searchParams.set(k, v)
    }
  }
  const res = await fetch(url)
  if (!res.ok) throw await toApiError(res)
  return res.json()
}
