import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listSubscriptions,
  addSymbol,
  removeSubscription,
  deleteStrategy,
  type Subscription,
} from '../api/strategy-api'

export function useSubscriptions(strategyCode: string | null) {
  return useQuery({
    queryKey: ['subscriptions', strategyCode],
    queryFn: () => listSubscriptions(strategyCode ?? undefined),
    enabled: !!strategyCode,
    // Poll while any subscription is still converging (desired ≠ actual), so the
    // forward-state badge tracks the reconcile loop without a manual refresh.
    refetchInterval: (q) => {
      const data = q.state.data as Subscription[] | undefined
      return data?.some((s) => s.desired_state !== s.actual_state) ? 2000 : false
    },
  })
}

export function useAddSymbol(strategyCode: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { symbol: string; interval: string }) =>
      addSymbol(strategyCode!, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['subscriptions', strategyCode] }),
  })
}

export function useRemoveSymbol(strategyCode: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (subId: string) => removeSubscription(subId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['subscriptions', strategyCode] }),
  })
}

export function useDeleteStrategy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (strategyCode: string) => deleteStrategy(strategyCode),
    onSuccess: (_, strategyCode) =>
      qc.invalidateQueries({ queryKey: ['subscriptions', strategyCode] }),
  })
}
