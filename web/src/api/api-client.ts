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

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(new URL(path, window.location.origin), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw await toApiError(res)
  return res.json()
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(new URL(path, window.location.origin), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw await toApiError(res)
  return res.json()
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
