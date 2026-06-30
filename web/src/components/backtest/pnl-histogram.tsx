import { useMemo, useCallback } from 'react'
import type { BacktestPosition } from '../../api/backtest-api'
import { HistogramChart } from './histogram-chart'
import { histogram, type HistogramBin } from './stats-utils'
import type { readChartColors } from '../../lib/theme-colors'

/** PnL distribution of closed positions — bins right of zero use the up color,
 *  bins left of zero the down color. */
export function PnlHistogram({ positions }: { positions: BacktestPosition[] }) {
  const bins = useMemo(
    () => histogram(positions.filter((p) => p.exit_time != null).map((p) => p.pnl)),
    [positions],
  )
  const colorFor = useCallback(
    (bin: HistogramBin, c: ReturnType<typeof readChartColors>) =>
      (bin.lo + bin.hi) / 2 >= 0 ? c.up : c.down,
    [],
  )
  return <HistogramChart bins={bins} colorFor={colorFor} emptyLabel="No closed positions." />
}
