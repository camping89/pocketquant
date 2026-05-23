/**
 * Fetch recent trades for a strategy subscription.
 * TODO(backend): implement GET /api/v1/strategies/{id}/trades endpoint.
 * Returns empty array until endpoint exists (404 → empty, no retry).
 */
import { useQuery } from '@tanstack/react-query'
import type { StrategyTrade } from '../components/strategies/recent-trades-table'
import type { Trade } from '../types/strategy'

/** Shape returned by the hook — extends StrategyTrade with Trade marker fields. */
export type { Trade }

async function fetchStrategyTrades(strategyId: string): Promise<StrategyTrade[]> {
  const res = await fetch(`/api/v1/strategies/${strategyId}/trades`)
  if (res.status === 404) return []
  if (!res.ok) throw new Error(`Trades fetch failed: ${res.status}`)
  return res.json() as Promise<StrategyTrade[]>
}

export function useStrategyTrades(strategyId: string | null) {
  return useQuery({
    queryKey: ['strategy-trades', strategyId],
    queryFn: () => fetchStrategyTrades(strategyId!),
    enabled: !!strategyId,
    // Do not retry on 404 — endpoint not yet implemented
    retry: (count, err: unknown) => {
      const msg = (err as Error)?.message ?? ''
      return !msg.includes('404') && count < 2
    },
    staleTime: 10_000,
  })
}
