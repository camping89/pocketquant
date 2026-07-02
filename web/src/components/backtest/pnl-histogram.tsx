import { useCallback } from 'react'
import type { HistogramBin } from '../../api/backtest-api'
import { HistogramChart } from './histogram-chart'
import type { readChartColors } from '../../lib/theme-colors'

/** PnL distribution of closed trades — bins right of zero use the up color,
 *  bins left of zero the down color. Bins are computed server-side. */
export function PnlHistogram({ bins }: { bins: HistogramBin[] }) {
  const colorFor = useCallback(
    (bin: HistogramBin, c: ReturnType<typeof readChartColors>) =>
      (bin.lo + bin.hi) / 2 >= 0 ? c.up : c.down,
    [],
  )
  return <HistogramChart bins={bins} colorFor={colorFor} emptyLabel="No closed trades." />
}
