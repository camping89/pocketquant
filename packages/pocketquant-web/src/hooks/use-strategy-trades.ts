/**
 * Fetch recent trades (closed positions) for a strategy subscription instance.
 * Backend: GET /api/v1/strategies/{strategy_id}/trades — newest-first list.
 */
import { useQuery } from '@tanstack/react-query'
import type { StrategyTrade } from '../components/strategies/recent-trades-table'
import type { Trade } from '../types/strategy'

/** Shape returned by the hook — extends StrategyTrade with Trade marker fields. */
export type { Trade }

async function fetchStrategyTrades(strategyId: string): Promise<StrategyTrade[]> {
  const res = await fetch(`/api/v1/strategies/${strategyId}/trades`)
  if (!res.ok) throw new Error(`Trades fetch failed: ${res.status}`)
  return res.json() as Promise<StrategyTrade[]>
}

export function useStrategyTrades(strategyId: string | null) {
  return useQuery({
    queryKey: ['strategy-trades', strategyId],
    queryFn: () => fetchStrategyTrades(strategyId!),
    enabled: !!strategyId,
    staleTime: 10_000,
    refetchInterval: 15_000,
  })
}
