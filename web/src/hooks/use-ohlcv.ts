import { useQuery } from '@tanstack/react-query'
import { fetchOHLCVBars } from '../api/market-data-api'
import { barsToChartData } from '../lib/chart-history'
import type { Interval } from '../types/market-data'

// Shared by every OHLCV observer and by the realtime-bar rollover invalidation. The cache
// holds raw desc-ordered bars; observers transform via select.
export function ohlcvQueryKey(symbol: string, interval: Interval) {
  return ['ohlcv', symbol, interval] as const
}

// The cache stores raw bars so the paginating observer can read them too.
export function useOHLCV(symbol: string, interval: Interval) {
  return useQuery({
    queryKey: ohlcvQueryKey(symbol, interval),
    queryFn: () => fetchOHLCVBars(symbol, interval),
    select: barsToChartData,
    staleTime: 5 * 60 * 1000,
    enabled: !!symbol,
  })
}
