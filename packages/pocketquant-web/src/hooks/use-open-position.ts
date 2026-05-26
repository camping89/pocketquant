/**
 * Fetch the open position for a subscription instance.
 * Backend: GET /api/v1/subscriptions/{sub_id}/positions — returns an array
 * (empty when no open position).
 */
import { useQuery } from '@tanstack/react-query'

/**
 * API response shape from GET /api/v1/subscriptions/{sub_id}/positions.
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

async function fetchOpenPosition(subId: string): Promise<OpenPosition | null> {
  const res = await fetch(`/api/v1/subscriptions/${subId}/positions`)
  if (!res.ok) throw new Error(`Positions fetch failed: ${res.status}`)
  const data = (await res.json()) as OpenPosition[]
  return data[0] ?? null
}

export function useOpenPosition(subId: string | null) {
  return useQuery({
    queryKey: ['open-position', subId],
    queryFn: () => fetchOpenPosition(subId!),
    enabled: !!subId,
    refetchInterval: 5_000,
    staleTime: 2_000,
  })
}
