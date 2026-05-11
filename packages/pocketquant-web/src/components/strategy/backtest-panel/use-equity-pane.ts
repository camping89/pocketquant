import { useEffect } from 'react'
import {
  AreaSeries,
  LineSeries,
  type IChartApi,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts'
import { toUTCTimestamp } from '../../../api/market-data-api'
import type { EquityPoint } from '../../../api/backtest-api'

/**
 * Add an equity + drawdown sub-pane to the main chart. Cleans up on unmount
 * so the sub-pane disappears when user switches away from the Equity tab.
 */
export function useEquityPane(chart: IChartApi | null, equityCurve: EquityPoint[]): void {
  useEffect(() => {
    if (!chart || equityCurve.length === 0) return

    // Add new pane (returned IPaneApi gives us the actual paneIndex)
    const equityPane = chart.addPane()
    const paneIndex = chart.panes().indexOf(equityPane)
    if (paneIndex < 0) return

    const equitySeries = chart.addSeries(
      LineSeries,
      {
        color: '#26a69a',
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
        priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
      },
      paneIndex,
    )

    const ddSeries = chart.addSeries(
      AreaSeries,
      {
        topColor: 'rgba(239,83,80,0.40)',
        bottomColor: 'rgba(239,83,80,0.00)',
        lineColor: '#ef5350',
        lineWidth: 1,
        priceScaleId: 'drawdown',
        priceLineVisible: false,
        lastValueVisible: false,
        priceFormat: { type: 'percent', precision: 2, minMove: 0.01 },
      },
      paneIndex,
    )

    // Set up the drawdown price scale on the right of the pane
    chart.priceScale('drawdown').applyOptions({
      scaleMargins: { top: 0.7, bottom: 0 },
      visible: true,
    })

    const equityData = equityCurve.map((p) => ({
      time: toUTCTimestamp(p.timestamp) as UTCTimestamp,
      value: p.equity,
    }))
    const ddData = equityCurve.map((p) => ({
      time: toUTCTimestamp(p.timestamp) as UTCTimestamp,
      value: p.drawdown * 100, // store as percent for display
    }))

    // Some equity points may share timestamps (multiple closes per fill); the
    // chart requires strictly increasing time per series — dedupe via Map.
    const dedupe = <T extends { time: Time }>(arr: T[]) => {
      const m = new Map<Time, T>()
      for (const p of arr) m.set(p.time, p)
      return Array.from(m.values()).sort(
        (a, b) => (a.time as number) - (b.time as number),
      )
    }

    equitySeries.setData(dedupe(equityData))
    ddSeries.setData(dedupe(ddData))

    // Stretch factors: main pane 3, equity pane 1
    const panes = chart.panes()
    if (panes.length >= 2) {
      panes[0].setStretchFactor(3)
      panes[paneIndex].setStretchFactor(1)
    }

    return () => {
      try {
        chart.removeSeries(equitySeries)
        chart.removeSeries(ddSeries)
        // After removing series the pane may still exist — remove it explicitly.
        const idx = chart.panes().indexOf(equityPane)
        if (idx > 0) chart.removePane(idx)
      } catch {
        // chart may have been disposed
      }
    }
  }, [chart, equityCurve])
}
