/**
 * Mutations for strategy lifecycle: start, stop, delete, create subscription.
 * Start/stop endpoints are stubbed — backend phase 6 will implement them.
 * TODO(phase-6): replace stub URLs with real /api/v1/strategies/{id}/start|stop
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { addSymbol, removeSymbol, deleteStrategy } from '../api/strategy-api'
import { ApiError } from '../api/strategy-api'

// ---------------------------------------------------------------------------
// Stub helpers — endpoints don't exist yet, will 404 gracefully
// ---------------------------------------------------------------------------

async function startStrategy(strategyId: string): Promise<void> {
  const res = await fetch(`/api/v1/strategies/${strategyId}/start`, { method: 'POST' })
  if (!res.ok) throw new ApiError(`Start failed: ${res.status}`, res.status)
}

async function stopStrategy(strategyId: string): Promise<void> {
  const res = await fetch(`/api/v1/strategies/${strategyId}/stop`, { method: 'POST' })
  if (!res.ok) throw new ApiError(`Stop failed: ${res.status}`, res.status)
}

// ---------------------------------------------------------------------------
// Exported hooks
// ---------------------------------------------------------------------------

export function useStartStrategy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (strategyId: string) => startStrategy(strategyId),
    onSuccess: (_, strategyId) => {
      qc.invalidateQueries({ queryKey: ['subscriptions', strategyId] })
    },
  })
}

export function useStopStrategy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (strategyId: string) => stopStrategy(strategyId),
    onSuccess: (_, strategyId) => {
      qc.invalidateQueries({ queryKey: ['subscriptions', strategyId] })
    },
  })
}

export function useDeleteSubscription(strategyId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (subId: string) => removeSymbol(strategyId!, subId),
    onSuccess: (_, subId) => {
      qc.invalidateQueries({ queryKey: ['subscriptions', strategyId] })
      qc.invalidateQueries({ queryKey: ['subscription-backtest', strategyId, subId] })
    },
  })
}

export function useDeleteStrategyById() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (strategyId: string) => deleteStrategy(strategyId),
    onSuccess: (_, strategyId) => {
      qc.invalidateQueries({ queryKey: ['subscriptions', strategyId] })
      qc.removeQueries({ queryKey: ['subscription-backtest', strategyId] })
      qc.invalidateQueries({ queryKey: ['strategies'] })
    },
  })
}

export function useCreateSubscription(strategyId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { symbol: string; interval: string }) =>
      addSymbol(strategyId!, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subscriptions', strategyId] })
    },
  })
}
