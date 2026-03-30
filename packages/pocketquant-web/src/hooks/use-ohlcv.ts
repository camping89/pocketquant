import { useQuery } from '@tanstack/react-query'
import { fetchOHLCV } from '../api/market-data-api'
import type { Interval } from '../types/market-data'

export function useOHLCV(exchange: string, symbol: string, interval: Interval) {
  return useQuery({
    queryKey: ['ohlcv', exchange, symbol, interval],
    queryFn: () => fetchOHLCV(exchange, symbol, interval),
    staleTime: 5 * 60 * 1000,
    enabled: !!exchange && !!symbol,
  })
}
