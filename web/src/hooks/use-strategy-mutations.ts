/**
 * Mutations for subscription lifecycle: start, stop, delete; template-scoped delete.
 *
 * Routes are split:
 *   /strategies/{strategy_code}/...     template-scoped
 *   /subscriptions/{sub_id}/...         instance-scoped
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { addSymbol, removeSubscription, deleteStrategy } from '../api/strategy-api'
import { apiPost } from '../api/api-client'

async function startSubscription(subId: string): Promise<void> {
  await apiPost(`/api/v1/subscriptions/${subId}/start`, {})
}

async function stopSubscription(subId: string): Promise<void> {
  await apiPost(`/api/v1/subscriptions/${subId}/stop`, {})
}

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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subscriptions', strategyCode] })
    },
  })
}

export function useDeleteStrategyById() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (strategyCode: string) => deleteStrategy(strategyCode),
    onSuccess: (_, strategyCode) => {
      qc.invalidateQueries({ queryKey: ['subscriptions', strategyCode] })
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
