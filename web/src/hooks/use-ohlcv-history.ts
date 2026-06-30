import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { fetchOHLCVBars } from '../api/market-data-api'
import { ohlcvQueryKey } from './use-ohlcv'
import {
  type BarMap,
  mergeBars,
  accToChartData,
  earliestCursor,
} from '../lib/chart-history'
import type { ChartData, Interval } from '../types/market-data'

const PAGE_SIZE = 1000

export interface OhlcvHistory {
  data: ChartData | undefined
  isLoading: boolean
  error: Error | null
  /** Fetch one older page (ending at the earliest accumulated bar). No-op while
   * a page is in flight, when no more history exists, or before the base load. */
  loadOlder: () => void
  isLoadingOlder: boolean
  /** False once a page older than the current earliest bar returns no new bars. */
  hasMore: boolean
}

/** OHLCV with scroll-left pagination. The base query (shared key with useOHLCV,
 * refetched on realtime rollover) supplies the latest page; loadOlder walks
 * backward via ``end_date``. All bars land in a time-keyed accumulator so the
 * sliding base window merges without dropping or duplicating boundary bars. */
export function useOhlcvHistory(symbol: string, interval: Interval): OhlcvHistory {
  const base = useQuery({
    queryKey: ohlcvQueryKey(symbol, interval),
    queryFn: () => fetchOHLCVBars(symbol, interval, PAGE_SIZE),
    staleTime: 5 * 60 * 1000,
    enabled: !!symbol,
  })

  const accRef = useRef<BarMap>(new Map())
  const [version, setVersion] = useState(0)
  const [isLoadingOlder, setIsLoadingOlder] = useState(false)
  const [hasMore, setHasMore] = useState(true)

  // Reset accumulator when the series identity changes — stale bars from a
  // previous symbol/interval must not bleed into the new chart.
  useEffect(() => {
    accRef.current = new Map()
    setVersion((v) => v + 1)
    setIsLoadingOlder(false)
    setHasMore(true)
  }, [symbol, interval])

  // Fold each base result (initial load + every rollover refetch) into the
  // accumulator. Overwrite-on-collision refreshes the latest bar's final close.
  useEffect(() => {
    if (!base.data) return
    mergeBars(accRef.current, base.data)
    setVersion((v) => v + 1)
  }, [base.data])

  const loadOlder = useCallback(() => {
    if (isLoadingOlder || !hasMore) return
    const cursor = earliestCursor(accRef.current)
    if (!cursor) return // base not loaded yet

    setIsLoadingOlder(true)
    void fetchOHLCVBars(symbol, interval, PAGE_SIZE, cursor)
      .then((bars) => {
        // The $lte boundary always re-returns the cursor bar; >1 net-new means
        // real history. <=1 (only the boundary, deduped) means we hit the start.
        const added = mergeBars(accRef.current, bars)
        if (added <= 1) setHasMore(false)
        setVersion((v) => v + 1)
      })
      .catch(() => {
        // transient fetch error — leave hasMore so the user can retry by scrolling
      })
      .finally(() => setIsLoadingOlder(false))
  }, [symbol, interval, isLoadingOlder, hasMore])

  const data = useMemo<ChartData | undefined>(() => {
    if (accRef.current.size === 0) return undefined
    return accToChartData(accRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version])

  return {
    data,
    isLoading: base.isLoading,
    error: base.error,
    loadOlder,
    isLoadingOlder,
    hasMore,
  }
}
