/**
 * Mutations for subscription lifecycle: start, stop, delete; template-scoped delete.
 *
 * Routes are split:
 *   /strategies/{strategy_code}/...     template-scoped
 *   /subscriptions/{sub_id}/...         instance-scoped
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { addSymbol, removeSubscription, deleteStrategy } from '../api/strategy-api'
import { ApiError } from '../api/strategy-api'

// ---------------------------------------------------------------------------
// Backend error envelope: { error: { code: string, message: string } }
// ---------------------------------------------------------------------------

async function extractErrorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const body = (await res.clone().json()) as
      | { error?: { code?: string; message?: string }; detail?: unknown }
      | undefined
    const msg = body?.error?.message
    if (msg) return msg
    if (typeof body?.detail === 'string') return body.detail
  } catch {
    // not JSON — try text
    try {
      const text = await res.text()
      if (text) return text.slice(0, 300)
    } catch {
      // ignore
    }
  }
  return fallback
}

async function startSubscription(subId: string): Promise<void> {
  const res = await fetch(`/api/v1/subscriptions/${subId}/start`, { method: 'POST' })
  if (!res.ok) {
    const detail = await extractErrorMessage(res, res.statusText || 'Unknown error')
    throw new ApiError(`Start failed (${res.status}): ${detail}`, res.status)
  }
}

async function stopSubscription(subId: string): Promise<void> {
  const res = await fetch(`/api/v1/subscriptions/${subId}/stop`, { method: 'POST' })
  if (!res.ok) {
    const detail = await extractErrorMessage(res, res.statusText || 'Unknown error')
    throw new ApiError(`Stop failed (${res.status}): ${detail}`, res.status)
  }
}

// ---------------------------------------------------------------------------
// Exported hooks
// ---------------------------------------------------------------------------

export function useStartStrategy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (subId: string) => startSubscription(subId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subscriptions'] })
    },
  })
}

export function useStopStrategy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (subId: string) => stopSubscription(subId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subscriptions'] })
    },
  })
}

export function useDeleteSubscription(strategyCode: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (subId: string) => removeSubscription(subId),
    onSuccess: (_, subId) => {
      qc.invalidateQueries({ queryKey: ['subscriptions', strategyCode] })
      qc.invalidateQueries({ queryKey: ['subscription-backtest', subId] })
    },
  })
}

export function useDeleteStrategyById() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (strategyCode: string) => deleteStrategy(strategyCode),
    onSuccess: (_, strategyCode) => {
      qc.invalidateQueries({ queryKey: ['subscriptions', strategyCode] })
      qc.removeQueries({ queryKey: ['subscription-backtest'] })
      qc.invalidateQueries({ queryKey: ['strategies'] })
    },
  })
}

export function useCreateSubscription(strategyCode: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { symbol: string; interval: string }) =>
      addSymbol(strategyCode!, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subscriptions', strategyCode] })
    },
  })
}
