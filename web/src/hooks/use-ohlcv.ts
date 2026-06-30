import { useQuery } from '@tanstack/react-query'
import { fetchOHLCVBars } from '../api/market-data-api'
import { barsToChartData } from '../lib/chart-history'
import type { Interval } from '../types/market-data'

/** react-query key shared by every OHLCV observer (chart, debug readout) and by
 * the realtime-bar rollover invalidation. The cache holds raw desc-ordered bars;
 * observers transform via ``select``. */
export function ohlcvQueryKey(symbol: string, interval: Interval) {
  return ['ohlcv', symbol, interval] as const
}

/** Fetch OHLCV bars for a composite symbol (e.g. "BTCUSDT:BINANCE"), shaped for
 * the chart. Cache stores raw bars so the paginating observer can read them too. */
export function useOHLCV(symbol: string, interval: Interval) {
  return useQuery({
    queryKey: ohlcvQueryKey(symbol, interval),
    queryFn: () => fetchOHLCVBars(symbol, interval),
    select: barsToChartData,
    staleTime: 5 * 60 * 1000,
    enabled: !!symbol,
  })
}
