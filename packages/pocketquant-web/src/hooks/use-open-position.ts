/**
 * Fetch open position(s) for a strategy subscription.
 * TODO(backend): implement GET /api/v1/strategies/{id}/positions endpoint.
 * Returns null until endpoint exists (404 → null, no retry).
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
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`Positions fetch failed: ${res.status}`)
  const data = await res.json() as OpenPosition[] | OpenPosition | null
  if (!data) return null
  // Handle both array and single object responses
  return Array.isArray(data) ? (data[0] ?? null) : data
}

export function useOpenPosition(strategyId: string | null) {
  return useQuery({
    queryKey: ['open-position', strategyId],
    queryFn: () => fetchOpenPosition(strategyId!),
    enabled: !!strategyId,
    retry: (count, err: unknown) => {
      const msg = (err as Error)?.message ?? ''
      return !msg.includes('404') && count < 2
    },
    refetchInterval: 5_000,
  })
}
