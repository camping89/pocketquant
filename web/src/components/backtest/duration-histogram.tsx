import { useCallback } from 'react'
import type { HistogramBin } from '../../api/backtest-api'
import { HistogramChart } from './histogram-chart'
import type { readChartColors } from '../../lib/theme-colors'

/** Holding-duration distribution (in hours) of closed trades. Bins are computed
 *  server-side. */
export function DurationHistogram({ bins }: { bins: HistogramBin[] }) {
  const colorFor = useCallback(
    (_bin: HistogramBin, c: ReturnType<typeof readChartColors>) => c.text,
    [],
  )
  return <HistogramChart bins={bins} colorFor={colorFor} emptyLabel="No closed trades." />
}
