import { useEffect, type RefObject } from 'react'
import type { ISeriesApi } from 'lightweight-charts'
import { toUTCTimestamp } from '../api/market-data-api'
import type { CurrentBarResponse, Interval } from '../types/market-data'

export function useRealtimeBar(
  exchange: string,
  symbol: string,
  interval: Interval,
  candleRef: RefObject<ISeriesApi<'Candlestick'> | null>,
  volumeRef: RefObject<ISeriesApi<'Histogram'> | null>,
) {
  useEffect(() => {
    const url = `/api/v1/market-data/bars/stream/${exchange}/${symbol}?interval=${interval}`
    const es = new EventSource(url)

    es.onmessage = (event) => {
      const candleSeries = candleRef.current
      const volumeSeries = volumeRef.current
      if (!candleSeries || !volumeSeries) return

      try {
        const bar: CurrentBarResponse = JSON.parse(event.data)
        if (bar.open === null || bar.close === null) return

        const time = toUTCTimestamp(bar.bar_start)
        candleSeries.update({
          time,
          open: bar.open,
          high: bar.high ?? bar.open,
          low: bar.low ?? bar.open,
          close: bar.close,
        })
        volumeSeries.update({
          time,
          value: bar.volume,
          color: bar.close >= bar.open
            ? 'rgba(38, 166, 154, 0.3)'
            : 'rgba(239, 83, 80, 0.3)',
        })
      } catch {
        // malformed event — ignore
      }
    }

    return () => es.close()
  }, [exchange, symbol, interval]) // eslint-disable-line react-hooks/exhaustive-deps
}
