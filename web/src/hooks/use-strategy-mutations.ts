// Every mutation invalidates ['subscriptions'], the key of the one list query.
// A longer key such as ['subscriptions', code] would not match it.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { addSymbol, removeSubscription } from '../api/strategy-api'
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

export function useDeleteSubscription() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (subId: string) => removeSubscription(subId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subscriptions'] })
    },
  })
}

export function useCreateSubscription(strategyCode: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { symbol: string; interval: string }) =>
      addSymbol(strategyCode!, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subscriptions'] })
    },
  })
}
