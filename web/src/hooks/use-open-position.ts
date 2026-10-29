import { useQuery } from '@tanstack/react-query'

// Uppercase direction matches the backend enum; strategies-page-layout adapts it to the chart OpenPosition.
export interface OpenPosition {
  symbol: string
  direction: 'LONG' | 'SHORT'
  entry_price: number
  quantity: number
  unrealized_pnl: number
  entry_time: string
  leverage?: number
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
