import { useQuery } from '@tanstack/react-query'
import type { StrategyTrade } from '../components/strategies/recent-trades-table'
import type { Trade } from '../types/strategy'

export type { Trade }

async function fetchSubscriptionTrades(subId: string): Promise<StrategyTrade[]> {
  const res = await fetch(`/api/v1/subscriptions/${subId}/trades`)
  if (!res.ok) throw new Error(`Trades fetch failed: ${res.status}`)
  return res.json() as Promise<StrategyTrade[]>
}

export function useStrategyTrades(subId: string | null) {
  return useQuery({
    queryKey: ['subscription-trades', subId],
    queryFn: () => fetchSubscriptionTrades(subId!),
    enabled: !!subId,
    staleTime: 10_000,
    refetchInterval: 15_000,
  })
}
