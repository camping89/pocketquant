import { useEffect, useRef } from 'react'
import {
  createChart,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from 'lightweight-charts'
import { readChartColors } from '../../lib/theme-colors'
import { useTheme } from '../../lib/use-theme'
import type { HistogramBin } from './stats-utils'

interface HistogramChartProps {
  bins: HistogramBin[]
  /** Bar color resolver per bin — lets PnL color wins/losses, duration use one tone. */
  colorFor: (bin: HistogramBin, colors: ReturnType<typeof readChartColors>) => string
  height?: number
  emptyLabel?: string
}

/** Bar chart over pre-binned values. Bins map to sequential integer "time" slots
 *  (lightweight-charts needs a time axis); the visual is a value distribution,
 *  not a time series. Theme-aware via readChartColors + re-color on theme flip. */
export function HistogramChart({ bins, colorFor, height = 200, emptyLabel = 'No data.' }: HistogramChartProps) {
  const { mode } = useTheme()
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const c = readChartColors()
    const chart = createChart(containerRef.current, {
      height,
      layout: { background: { color: 'transparent' }, textColor: c.text },
      grid: { vertLines: { visible: false }, horzLines: { color: c.grid } },
      rightPriceScale: { borderColor: c.border },
      timeScale: { borderColor: c.border, visible: false },
      crosshair: { horzLine: { visible: false }, vertLine: { visible: false } },
    })
    const series = chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false })
    chartRef.current = chart
    seriesRef.current = series

    const ro = new ResizeObserver((entries) => chart.applyOptions({ width: entries[0].contentRect.width }))
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [height])

  // Re-bind data + themed colors. Depends on `mode` too so a dark/light flip
  // recomputes bar colors and axis tokens without a separate effect.
  useEffect(() => {
    if (!seriesRef.current) return
    const c = readChartColors()
    chartRef.current?.applyOptions({
      layout: { textColor: c.text },
      grid: { horzLines: { color: c.grid } },
      rightPriceScale: { borderColor: c.border },
    })
    seriesRef.current.setData(
      bins.map((bin, i) => ({ time: (i + 1) as Time, value: bin.count, color: colorFor(bin, c) })),
    )
    chartRef.current?.timeScale().fitContent()
  }, [bins, colorFor, mode])

  if (bins.length === 0) {
    return <div className="empty-state" style={{ padding: 16 }}>{emptyLabel}</div>
  }
  return <div ref={containerRef} style={{ width: '100%' }} />
}
