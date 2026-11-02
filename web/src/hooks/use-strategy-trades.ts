import { useQuery } from '@tanstack/react-query'
import { apiFetchAdmin } from '../api/api-client'
import type { Trade } from '../types/strategy'

export type { Trade }

// A closed position: the backend's completed trade.
export interface StrategyTrade {
  id: string
  direction: 'LONG' | 'SHORT'
  entry_price: number
  exit_price: number | null
  entry_time: string
  exit_time: string | null
  pnl: number
  quantity: number
}

export function useStrategyTrades(subId: string | null) {
  return useQuery({
    queryKey: ['subscription-trades', subId],
    queryFn: () => apiFetchAdmin<StrategyTrade[]>(`/api/v1/subscriptions/${subId}/trades`),
    enabled: !!subId,
    staleTime: 10_000,
    refetchInterval: 15_000,
  })
}
