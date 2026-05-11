import { useEffect, useRef, useState, type RefObject } from 'react'
import type { ISeriesApi } from 'lightweight-charts'
import { useQueryClient } from '@tanstack/react-query'
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
// Delay before re-fetching historical OHLCV after a bar rollover or SSE
// reconnect — long enough for sync_1m + cascade to write the just-closed
// bar's authoritative final close to Mongo.
const REFETCH_DELAY_MS = 5_000

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
  const queryClient = useQueryClient()

  // Refs that survive re-renders and are safe to read/write inside effects
  const lastBarStartRef = useRef<number | null>(null)
  const lastUpdateTsRef = useRef<number | null>(null)

  useEffect(() => {
    // Reset per-session tracking inside the effect (not during render)
    lastBarStartRef.current = null
    lastUpdateTsRef.current = null

    const url = `/api/v1/market-data/bars/stream/${exchange}/${symbol}?interval=${interval}`
    const es = new EventSource(url)
    const ohlcvQueryKey = ['ohlcv', exchange, symbol, interval] as const
    const refetchTimers: ReturnType<typeof setTimeout>[] = []

    const scheduleOhlcvRefetch = () => {
      const t = setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ohlcvQueryKey })
      }, REFETCH_DELAY_MS)
      refetchTimers.push(t)
    }

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

        // Bar rollover: the just-closed previous bar may have a stale close in
        // the chart (SSE doesn't push the final close on completion). Refetch
        // historical OHLCV so the closed bar gets its authoritative close from
        // Mongo and any visual gap with the new bar disappears.
        const isRollover = lastBarStartRef.current !== null && time > lastBarStartRef.current
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

        if (isRollover) scheduleOhlcvRefetch()

        const now = Date.now()
        lastUpdateTsRef.current = now
        setLastUpdateTs(now)
        setIsStale(false)
        setIsInProgress(bar.is_in_progress ?? false)
      } catch {
        // malformed event — ignore
      }
    }

    // EventSource auto-reconnects on transient drops, but events emitted during
    // the gap are lost. Trigger an OHLCV refetch so the chart resyncs to Mongo
    // state once the connection is restored.
    es.onerror = () => {
      setIsStale(true)
      scheduleOhlcvRefetch()
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
      for (const t of refetchTimers) clearTimeout(t)
    }
  }, [exchange, symbol, interval]) // eslint-disable-line react-hooks/exhaustive-deps

  return { lastUpdateTs, isStale, isInProgress }
}
