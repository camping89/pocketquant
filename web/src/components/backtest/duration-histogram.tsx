import { useMemo, useCallback } from 'react'
import type { BacktestPosition } from '../../api/backtest-api'
import { HistogramChart } from './histogram-chart'
import { histogram, type HistogramBin } from './stats-utils'
import type { readChartColors } from '../../lib/theme-colors'

const HOUR = 3600

/** Holding-duration distribution (in hours) of closed positions. */
export function DurationHistogram({ positions }: { positions: BacktestPosition[] }) {
  const bins = useMemo(() => {
    const hours = positions
      .filter((p) => p.exit_time != null)
      .map((p) => {
        const start = new Date(p.entry_time).getTime()
        const end = new Date(p.exit_time as string).getTime()
        return (end - start) / 1000 / HOUR
      })
      .filter((h) => isFinite(h) && h >= 0)
    return histogram(hours)
  }, [positions])

  const colorFor = useCallback(
    (_bin: HistogramBin, c: ReturnType<typeof readChartColors>) => c.text,
    [],
  )
  return <HistogramChart bins={bins} colorFor={colorFor} emptyLabel="No closed positions." />
}
