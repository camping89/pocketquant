// Every mutation invalidates ['subscriptions'], the key of the one list query.
// A longer key such as ['subscriptions', code] would not match it.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  addSymbol,
  editSubscription,
  removeSubscription,
  requestAction,
  type ManualAction,
} from '../api/strategy-api'
import { apiPost } from '../api/api-client'
import type { Broker } from '../lib/money-hint'

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
    mutationFn: (body: {
      symbol: string
      intervals: string[]
      parameters: Record<string, unknown>
      broker: Broker
    }) => addSymbol(strategyCode!, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subscriptions'] })
    },
  })
}

export function useEditSubscription() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; intervals: string[]; parameters: Record<string, unknown> }) =>
      editSubscription(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subscriptions'] })
    },
  })
}

export function useSubscriptionAction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: ManualAction }) => requestAction(id, action),
    // Returning the refetch keeps the mutation pending until the row shows the queued
    // action, so the button cannot be pressed again in between.
    onSuccess: (_data, { id }) =>
      Promise.all([
        qc.invalidateQueries({ queryKey: ['subscriptions'] }),
        qc.invalidateQueries({ queryKey: ['subscription-orders', id] }),
        qc.invalidateQueries({ queryKey: ['subscription-snapshot', id] }),
      ]),
  })
}
