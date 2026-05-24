/**
 * Fetch the open position for a strategy subscription instance.
 * Backend: GET /api/v1/strategies/{strategy_id}/positions — returns an array
 * (empty when no open position).
 */
import { useQuery } from '@tanstack/react-query'

/**
 * API response shape from GET /api/v1/strategies/{id}/positions.
 * Uses uppercase direction to match backend enum; adapted to chart OpenPosition in strategies-page-layout.
 */
export interface OpenPosition {
  symbol: string
  direction: 'LONG' | 'SHORT'
  entry_price: number
  quantity: number
  unrealized_pnl: number
  entry_time: string
  leverage?: number
  /** Liquidation price if available from the exchange. */
  liq_price?: number | null
}

async function fetchOpenPosition(strategyId: string): Promise<OpenPosition | null> {
  const res = await fetch(`/api/v1/strategies/${strategyId}/positions`)
  if (!res.ok) throw new Error(`Positions fetch failed: ${res.status}`)
  const data = await res.json() as OpenPosition[]
  return data[0] ?? null
}

export function useOpenPosition(strategyId: string | null) {
  return useQuery({
    queryKey: ['open-position', strategyId],
    queryFn: () => fetchOpenPosition(strategyId!),
    enabled: !!strategyId,
    refetchInterval: 5_000,
    staleTime: 2_000,
  })
}
