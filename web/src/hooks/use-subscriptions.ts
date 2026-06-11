import { useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listSubscriptions,
  addSymbol,
  removeSubscription,
  runAllBacktests,
  getSubscriptionBacktest,
  deleteStrategy,
  type Subscription,
} from '../api/strategy-api'

export function useSubscriptions(strategyCode: string | null) {
  const qc = useQueryClient()
  const prevStatusesRef = useRef<Record<string, string>>({})

  const query = useQuery({
    queryKey: ['subscriptions', strategyCode],
    queryFn: () => listSubscriptions(strategyCode ?? undefined),
    enabled: !!strategyCode,
    refetchInterval: (q) => {
      const data = q.state.data as Subscription[] | undefined
      return data?.some((s) => s.backtest?.status === 'running') ? 2000 : false
    },
  })

  // Invalidate per-sub backtest cache when a subscription transitions out of 'running'
  useEffect(() => {
    if (!strategyCode) return
    const subs = query.data ?? []
    const prev = prevStatusesRef.current
    const next: Record<string, string> = {}
    for (const sub of subs) {
      const status = sub.backtest?.status ?? 'none'
      next[sub.id] = status
      if (prev[sub.id] === 'running' && status !== 'running') {
        qc.invalidateQueries({ queryKey: ['subscription-backtest', sub.id] })
      }
    }
    prevStatusesRef.current = next
  }, [query.data, qc, strategyCode])

  return query
}

export function useSubscriptionBacktest(subId: string | null) {
  return useQuery({
    queryKey: ['subscription-backtest', subId],
    queryFn: () => getSubscriptionBacktest(subId!),
    enabled: !!subId,
    // Do not retry on 404 (no backtest run yet), limit other retries to 2
    retry: (count, err: unknown) => {
      const status = (err as { status?: number })?.status
      return status !== 404 && count < 2
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
    onSuccess: (_, subId) => {
      qc.invalidateQueries({ queryKey: ['subscriptions', strategyCode] })
      qc.invalidateQueries({ queryKey: ['subscription-backtest', subId] })
    },
  })
}

export function useRunAllBacktests(strategyCode: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => runAllBacktests(strategyCode!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['subscriptions', strategyCode] }),
  })
}

export function useDeleteStrategy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (strategyCode: string) => deleteStrategy(strategyCode),
    onSuccess: (_, strategyCode) => {
      qc.invalidateQueries({ queryKey: ['subscriptions', strategyCode] })
      qc.removeQueries({ queryKey: ['subscription-backtest'] })
    },
  })
}
