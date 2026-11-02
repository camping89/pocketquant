import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiPost } from './api-client'

function memoryStorage(): Storage {
  const data = new Map<string, string>()
  return {
    get length() {
      return data.size
    },
    clear: () => data.clear(),
    getItem: (k) => data.get(k) ?? null,
    key: (i) => [...data.keys()][i] ?? null,
    removeItem: (k) => void data.delete(k),
    setItem: (k, v) => void data.set(k, v),
  }
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function sentToken(fetchMock: ReturnType<typeof vi.fn>, call: number): string | null {
  const init = fetchMock.mock.calls[call][1] as RequestInit
  return new Headers(init.headers).get('X-Admin-Token')
}

describe('admin token on mutations', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  let prompt: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    prompt = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('localStorage', memoryStorage())
    vi.stubGlobal('window', { location: { origin: 'http://test' }, prompt })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends the stored token', async () => {
    localStorage.setItem('pq.adminToken', 'stored')
    fetchMock.mockResolvedValueOnce(json(200, { ok: true }))

    await apiPost('/api/v1/x', {})

    expect(sentToken(fetchMock, 0)).toBe('stored')
    expect(prompt).not.toHaveBeenCalled()
  })

  it('prompts once on 401 and retries once with the new token', async () => {
    prompt.mockReturnValue('fresh')
    fetchMock
      .mockResolvedValueOnce(json(401, { detail: 'Invalid or missing X-Admin-Token' }))
      .mockResolvedValueOnce(json(200, { ok: true }))

    await expect(apiPost('/api/v1/x', {})).resolves.toEqual({ ok: true })

    expect(prompt).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(sentToken(fetchMock, 1)).toBe('fresh')
    expect(localStorage.getItem('pq.adminToken')).toBe('fresh')
  })

  it('throws ApiError 401 when the retry is also rejected', async () => {
    prompt.mockReturnValue('still-wrong')
    fetchMock.mockImplementation(async () =>
      json(401, { detail: 'Invalid or missing X-Admin-Token' }),
    )

    const err = await apiPost('/api/v1/x', {}).catch((e: unknown) => e)

    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(401)
    expect(prompt).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})

describe('admin token on reads', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  let prompt: ReturnType<typeof vi.fn>

  // The declined flag lives for the page load, so each test gets a fresh module.
  async function load() {
    vi.resetModules()
    return import('./api-client')
  }

  beforeEach(() => {
    fetchMock = vi.fn()
    prompt = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('localStorage', memoryStorage())
    vi.stubGlobal('window', { location: { origin: 'http://test' }, prompt })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends the stored token on a read', async () => {
    const api = await load()
    localStorage.setItem('pq.adminToken', 'stored')
    fetchMock.mockResolvedValueOnce(json(200, [1]))

    await expect(api.apiFetchAdmin('/api/v1/x')).resolves.toEqual([1])

    expect(sentToken(fetchMock, 0)).toBe('stored')
    expect(prompt).not.toHaveBeenCalled()
  })

  it('prompts once on a read 401 and retries with the new token', async () => {
    const api = await load()
    prompt.mockReturnValue('fresh')
    fetchMock
      .mockResolvedValueOnce(json(401, { detail: 'Invalid or missing X-Admin-Token' }))
      .mockResolvedValueOnce(json(200, [1]))

    await expect(api.apiFetchAdmin('/api/v1/x')).resolves.toEqual([1])

    expect(prompt).toHaveBeenCalledTimes(1)
    expect(sentToken(fetchMock, 1)).toBe('fresh')
  })

  it('does not prompt again after a declined read prompt', async () => {
    const api = await load()
    prompt.mockReturnValue(null)
    fetchMock.mockImplementation(async () => json(401, { detail: 'Invalid or missing X-Admin-Token' }))

    const first = await api.apiFetchAdmin('/api/v1/x').catch((e: unknown) => e)
    const second = await api.apiFetchAdmin('/api/v1/x').catch((e: unknown) => e)

    for (const err of [first, second]) {
      expect(err).toBeInstanceOf(api.ApiError)
      expect((err as InstanceType<typeof api.ApiError>).status).toBe(401)
    }
    expect(prompt).toHaveBeenCalledTimes(1)
  })

  it('still prompts on a mutation after a declined read prompt', async () => {
    const api = await load()
    prompt.mockReturnValue(null)
    fetchMock.mockImplementation(async () => json(401, { detail: 'Invalid or missing X-Admin-Token' }))

    await api.apiFetchAdmin('/api/v1/x').catch(() => undefined)
    await api.apiPost('/api/v1/x', {}).catch(() => undefined)

    expect(prompt).toHaveBeenCalledTimes(2)
  })

  it('retries a read silently when a newer token was stored meanwhile', async () => {
    const api = await load()
    localStorage.setItem('pq.adminToken', 'old')
    fetchMock
      .mockImplementationOnce(async () => {
        localStorage.setItem('pq.adminToken', 'new')
        return json(401, { detail: 'Invalid or missing X-Admin-Token' })
      })
      .mockResolvedValueOnce(json(200, [1]))

    await expect(api.apiFetchAdmin('/api/v1/x')).resolves.toEqual([1])

    expect(sentToken(fetchMock, 1)).toBe('new')
    expect(prompt).not.toHaveBeenCalled()
  })
})
