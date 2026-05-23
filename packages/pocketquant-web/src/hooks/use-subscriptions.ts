import { useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listSymbols,
  addSymbol,
  removeSymbol,
  runAllBacktests,
  getSubscriptionBacktest,
  deleteStrategy,
  type Subscription,
} from '../api/strategy-api'

export function useSubscriptions(strategyId: string | null) {
  const qc = useQueryClient()
  const prevStatusesRef = useRef<Record<string, string>>({})

  const query = useQuery({
    queryKey: ['subscriptions', strategyId],
    queryFn: () => listSymbols(strategyId!),
    enabled: !!strategyId,
    refetchInterval: (q) => {
      const data = q.state.data as Subscription[] | undefined
      return data?.some((s) => s.backtest?.status === 'running') ? 2000 : false
    },
  })

  // M3: Invalidate per-sub backtest cache when a subscription transitions out of 'running'
  useEffect(() => {
    if (!strategyId) return
    const subs = query.data ?? []
    const prev = prevStatusesRef.current
    const next: Record<string, string> = {}
    for (const sub of subs) {
      const status = sub.backtest?.status ?? 'none'
      next[sub.id] = status
      if (prev[sub.id] === 'running' && status !== 'running') {
        qc.invalidateQueries({ queryKey: ['subscription-backtest', strategyId, sub.id] })
      }
    }
    prevStatusesRef.current = next
  }, [query.data, qc, strategyId])

  return query
}

export function useSubscriptionBacktest(strategyId: string | null, subId: string | null) {
  return useQuery({
    queryKey: ['subscription-backtest', strategyId, subId],
    queryFn: () => getSubscriptionBacktest(strategyId!, subId!),
    enabled: !!strategyId && !!subId,
    // Do not retry on 404 (no backtest run yet), limit other retries to 2
    retry: (count, err: unknown) => {
      const status = (err as { status?: number })?.status
      return status !== 404 && count < 2
    },
  })
}

export function useAddSymbol(strategyId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { symbol: string; interval: string }) =>
      addSymbol(strategyId!, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['subscriptions', strategyId] }),
  })
}

export function useRemoveSymbol(strategyId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (subId: string) => removeSymbol(strategyId!, subId),
    onSuccess: (_, subId) => {
      qc.invalidateQueries({ queryKey: ['subscriptions', strategyId] })
      qc.invalidateQueries({ queryKey: ['subscription-backtest', strategyId, subId] })
    },
  })
}

export function useRunAllBacktests(strategyId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => runAllBacktests(strategyId!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['subscriptions', strategyId] }),
  })
}

export function useDeleteStrategy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (strategyId: string) => deleteStrategy(strategyId),
    onSuccess: (_, strategyId) => {
      qc.invalidateQueries({ queryKey: ['subscriptions', strategyId] })
      qc.removeQueries({ queryKey: ['subscription-backtest', strategyId] })
    },
  })
}
