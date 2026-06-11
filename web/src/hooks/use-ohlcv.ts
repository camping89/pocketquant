import { useQuery } from '@tanstack/react-query'
import { fetchOHLCV } from '../api/market-data-api'
import type { Interval } from '../types/market-data'

/** Fetch OHLCV bars for a composite symbol (e.g. "BTCUSDT:BINANCE"). */
export function useOHLCV(symbol: string, interval: Interval) {
  return useQuery({
    queryKey: ['ohlcv', symbol, interval],
    queryFn: () => fetchOHLCV(symbol, interval),
    staleTime: 5 * 60 * 1000,
    enabled: !!symbol,
  })
}
