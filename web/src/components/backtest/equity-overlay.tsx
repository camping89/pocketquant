import { useEffect, useRef } from 'react'
import {
  createChart,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Time,
} from 'lightweight-charts'
import type { BacktestRunResult } from '../../api/backtest-api'
import { parseIso } from '../../lib/datetime'
import { readChartColors } from '../../lib/theme-colors'
import { useTheme } from '../../lib/use-theme'

const SERIES_COLORS = ['#4A9782', '#C96442', '#6c8eef']

const toTime = (iso: string): Time => ((parseIso(iso)?.valueOf() ?? 0) / 1000) as Time

/** Normalize an equity curve to % return off the run's first point. Cross-scope
 *  runs have different price levels, so % is the only comparable axis (Q2). */
function toPercentSeries(run: BacktestRunResult): LineData[] {
  const curve = run.equity_curve
  if (curve.length === 0) return []
  const base = curve[0].equity
  if (base === 0) return []
  return curve.map((p) => ({ time: toTime(p.timestamp), value: (p.equity / base - 1) * 100 }))
}

/** Overlay multiple runs' equity curves, each normalized to % return. */
export function EquityOverlay({ runs }: { runs: BacktestRunResult[] }) {
  const { mode } = useTheme()
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Line'>[]>([])

  useEffect(() => {
    if (!containerRef.current) return
    const c = readChartColors()
    const chart = createChart(containerRef.current, {
      height: 320,
      layout: { background: { color: 'transparent' }, textColor: c.text },
      grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
      rightPriceScale: { borderColor: c.border },
      timeScale: { borderColor: c.border, timeVisible: true },
    })
    chartRef.current = chart
    const ro = new ResizeObserver((entries) => chart.applyOptions({ width: entries[0].contentRect.width }))
    ro.observe(containerRef.current)
    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
      seriesRef.current = []
    }
  }, [])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    for (const s of seriesRef.current) chart.removeSeries(s)
    seriesRef.current = runs.map((run, i) => {
      const series = chart.addSeries(LineSeries, {
        color: SERIES_COLORS[i % SERIES_COLORS.length],
        lineWidth: 2,
        priceLineVisible: false,
        priceFormat: { type: 'percent' },
      })
      series.setData(toPercentSeries(run))
      return series
    })
    chart.timeScale().fitContent()
  }, [runs])

  useEffect(() => {
    const c = readChartColors()
    chartRef.current?.applyOptions({
      layout: { textColor: c.text },
      grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
      rightPriceScale: { borderColor: c.border },
      timeScale: { borderColor: c.border },
    })
  }, [mode])

  return <div ref={containerRef} style={{ width: '100%' }} />
}

export { SERIES_COLORS }
