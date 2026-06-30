import { useEffect, useRef } from 'react'
import {
  createChart,
  LineSeries,
  AreaSeries,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Time,
} from 'lightweight-charts'
import type { EquityPoint } from '../../api/backtest-api'
import { parseIso } from '../../lib/datetime'
import { readChartColors } from '../../lib/theme-colors'
import { useTheme } from '../../lib/use-theme'

interface EquityDrawdownChartProps {
  equityCurve: EquityPoint[]
}

const baseChartOptions = (height: number) => {
  const c = readChartColors()
  return {
    height,
    layout: { background: { color: 'transparent' }, textColor: c.text },
    grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
    rightPriceScale: { borderColor: c.border },
    timeScale: { borderColor: c.border, timeVisible: true },
  }
}

const toTime = (iso: string): Time => ((parseIso(iso)?.valueOf() ?? 0) / 1000) as Time

/** Full-width equity line + underwater (drawdown) area. Two stacked charts share
 *  the time axis; drawdown comes per-point from the run doc so it stays exact. */
export function EquityDrawdownChart({ equityCurve }: EquityDrawdownChartProps) {
  const { mode } = useTheme()
  const equityRef = useRef<HTMLDivElement>(null)
  const underwaterRef = useRef<HTMLDivElement>(null)
  const equityChart = useRef<IChartApi | null>(null)
  const underwaterChart = useRef<IChartApi | null>(null)
  const equitySeries = useRef<ISeriesApi<'Line'> | null>(null)
  const underwaterSeries = useRef<ISeriesApi<'Area'> | null>(null)

  useEffect(() => {
    if (!equityRef.current || !underwaterRef.current) return
    const c = readChartColors()

    const eChart = createChart(equityRef.current, baseChartOptions(220))
    const eSeries = eChart.addSeries(LineSeries, {
      color: c.up,
      lineWidth: 2,
      priceLineVisible: false,
    })
    const uChart = createChart(underwaterRef.current, baseChartOptions(110))
    const uSeries = uChart.addSeries(AreaSeries, {
      lineColor: c.down,
      topColor: c.down,
      bottomColor: 'transparent',
      lineWidth: 1,
      priceLineVisible: false,
    })

    equityChart.current = eChart
    underwaterChart.current = uChart
    equitySeries.current = eSeries
    underwaterSeries.current = uSeries

    const ro = new ResizeObserver((entries) => {
      const w = entries[0].contentRect.width
      eChart.applyOptions({ width: w })
      uChart.applyOptions({ width: w })
    })
    ro.observe(equityRef.current)

    return () => {
      ro.disconnect()
      eChart.remove()
      uChart.remove()
      equityChart.current = null
      underwaterChart.current = null
      equitySeries.current = null
      underwaterSeries.current = null
    }
  }, [])

  useEffect(() => {
    if (!equitySeries.current || !underwaterSeries.current) return
    const equityData: LineData[] = equityCurve.map((p) => ({ time: toTime(p.timestamp), value: p.equity }))
    // Drawdown is stored negative; plot as a positive depth so the area dips below.
    const underwaterData: LineData[] = equityCurve.map((p) => ({
      time: toTime(p.timestamp),
      value: p.drawdown * 100,
    }))
    equitySeries.current.setData(equityData)
    underwaterSeries.current.setData(underwaterData)
    equityChart.current?.timeScale().fitContent()
    underwaterChart.current?.timeScale().fitContent()
  }, [equityCurve])

  // Re-apply themed colors on dark/light flip (charts persist, series intact).
  useEffect(() => {
    const c = readChartColors()
    for (const chart of [equityChart.current, underwaterChart.current]) {
      chart?.applyOptions({
        layout: { background: { color: 'transparent' }, textColor: c.text },
        grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
        rightPriceScale: { borderColor: c.border },
        timeScale: { borderColor: c.border },
      })
    }
    equitySeries.current?.applyOptions({ color: c.up })
    underwaterSeries.current?.applyOptions({ lineColor: c.down, topColor: c.down })
  }, [mode])

  if (equityCurve.length === 0) {
    return <div className="empty-state" style={{ padding: 16 }}>No equity data.</div>
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div ref={equityRef} style={{ width: '100%' }} />
      <div style={{ fontSize: 10, color: 'var(--text-secondary)', paddingLeft: 4 }}>Underwater (drawdown %)</div>
      <div ref={underwaterRef} style={{ width: '100%' }} />
    </div>
  )
}
