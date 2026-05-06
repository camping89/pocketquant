import { useEffect, useRef, useState, type RefObject } from 'react'
import type { ISeriesApi } from 'lightweight-charts'
import { toUTCTimestamp } from '../api/market-data-api'
import type { CurrentBarResponse, Interval } from '../types/market-data'

export interface RealtimeBarState {
  lastUpdateTs: number | null
  isStale: boolean
  isInProgress: boolean | null
}

// isStale threshold: no SSE event received for >30s
const STALE_THRESHOLD_MS = 30_000
// How often the stale check timer fires
const STALE_CHECK_INTERVAL_MS = 5_000

export function useRealtimeBar(
  exchange: string,
  symbol: string,
  interval: Interval,
  candleRef: RefObject<ISeriesApi<'Candlestick'> | null>,
  volumeRef: RefObject<ISeriesApi<'Histogram'> | null>,
): RealtimeBarState {
  const [lastUpdateTs, setLastUpdateTs] = useState<number | null>(null)
  const [isStale, setIsStale] = useState(false)
  const [isInProgress, setIsInProgress] = useState<boolean | null>(null)

  // Refs that survive re-renders and are safe to read/write inside effects
  const lastBarStartRef = useRef<number | null>(null)
  const lastUpdateTsRef = useRef<number | null>(null)

  useEffect(() => {
    // Reset per-session tracking inside the effect (not during render)
    lastBarStartRef.current = null
    lastUpdateTsRef.current = null

    const url = `/api/v1/market-data/bars/stream/${exchange}/${symbol}?interval=${interval}`
    const es = new EventSource(url)

    es.onmessage = (event) => {
      const candleSeries = candleRef.current
      const volumeSeries = volumeRef.current
      if (!candleSeries || !volumeSeries) return

      try {
        const bar: CurrentBarResponse = JSON.parse(event.data as string)
        if (bar.open === null || bar.close === null) return

        const time = toUTCTimestamp(bar.bar_start)

        // Enforce monotonic time — skip out-of-order events to prevent chart crash
        if (lastBarStartRef.current !== null && time < lastBarStartRef.current) return
        lastBarStartRef.current = time

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

        const now = Date.now()
        lastUpdateTsRef.current = now
        setLastUpdateTs(now)
        setIsStale(false)
        setIsInProgress(bar.is_in_progress ?? false)
      } catch {
        // malformed event — ignore
      }
    }

    // Periodically re-evaluate staleness so the indicator updates without an SSE event
    const staleTimer = setInterval(() => {
      const ts = lastUpdateTsRef.current
      if (ts !== null) {
        setIsStale(Date.now() - ts > STALE_THRESHOLD_MS)
      }
    }, STALE_CHECK_INTERVAL_MS)

    return () => {
      es.close()
      clearInterval(staleTimer)
    }
  }, [exchange, symbol, interval]) // eslint-disable-line react-hooks/exhaustive-deps

  return { lastUpdateTs, isStale, isInProgress }
}
