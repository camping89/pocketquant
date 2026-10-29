import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchSyncStatus } from '../api/market-data-api'
import type { Interval } from '../types/market-data'

export const INTERVAL_ORDER: Interval[] = [
  '1m', '5m', '15m',
  '1h', '4h',
  '1d', '1w',
]

const INTERVAL_LABELS: Record<Interval, string> = {
  '1m': '1m', '5m': '5m', '15m': '15m',
  '1h': '1h', '4h': '4h',
  '1d': '1D', '1w': '1W',
}

export interface IntervalOption {
  label: string
  value: Interval
  // False when no completed sync entry exists for this symbol and interval.
  available: boolean
}

export function useAvailableIntervals(symbol: string): IntervalOption[] {
  const { data: syncStatuses } = useQuery({
    queryKey: ['sync-status'],
    queryFn: fetchSyncStatus,
    staleTime: 60 * 1000,
  })

  return useMemo(() => {
    const available = new Set(
      (syncStatuses ?? [])
        .filter((s) => s.symbol === symbol && s.status === 'completed')
        .map((s) => s.interval),
    )

    return INTERVAL_ORDER.map((iv) => ({
      label: INTERVAL_LABELS[iv],
      value: iv,
      available: available.has(iv),
    }))
  }, [syncStatuses, symbol])
}
