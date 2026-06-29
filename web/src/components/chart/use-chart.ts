import { useEffect, useRef, type RefObject } from 'react'
import {
  createChart,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type DeepPartial,
  type ChartOptions,
} from 'lightweight-charts'
import { makeChartTimeFormatter, type TimezoneMode } from '../../lib/datetime'
import { readChartColors } from '../../lib/theme-colors'
import type { ThemeMode } from '../../lib/theme-context'

function themedOptions(): DeepPartial<ChartOptions> {
  const c = readChartColors()
  return {
    layout: {
      background: { type: ColorType.Solid, color: c.background },
      textColor: c.text,
    },
    grid: {
      vertLines: { color: c.grid },
      horzLines: { color: c.grid },
    },
    crosshair: { mode: CrosshairMode.Normal },
    rightPriceScale: { borderColor: c.border },
    timeScale: { borderColor: c.border, timeVisible: true },
  }
}

export function useChart(
  containerRef: RefObject<HTMLDivElement | null>,
  options?: DeepPartial<ChartOptions>,
  mode: TimezoneMode = 'utc',
  themeMode: ThemeMode = 'dark',
) {
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const initFormatter = makeChartTimeFormatter(mode)
    const base = themedOptions()
    const chart = createChart(el, {
      ...base,
      ...options,
      localization: {
        ...base.localization,
        ...options?.localization,
        timeFormatter: initFormatter,
      },
      timeScale: {
        ...base.timeScale,
        ...options?.timeScale,
        tickMarkFormatter: initFormatter,
      },
    })
    chartRef.current = chart

    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect
      chart.applyOptions({ width, height })
    })
    ro.observe(el)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Live formatter swap on mode change — chart instance preserved (zoom/series intact).
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    const formatter = makeChartTimeFormatter(mode)
    // localization.timeFormatter drives crosshair label;
    // timeScale.tickMarkFormatter drives axis tick labels — apply both.
    chart.applyOptions({
      localization: { timeFormatter: formatter },
      timeScale: { tickMarkFormatter: formatter },
    })
  }, [mode])

  // Re-apply layout/grid/scale colors on theme flip — instance preserved
  // (zoom/series intact). Candle colors are re-applied by the chart components
  // themselves (they own the series refs).
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    const c = readChartColors()
    chart.applyOptions({
      layout: {
        background: { type: ColorType.Solid, color: c.background },
        textColor: c.text,
      },
      grid: {
        vertLines: { color: c.grid },
        horzLines: { color: c.grid },
      },
      rightPriceScale: { borderColor: c.border },
      timeScale: { borderColor: c.border },
    })
  }, [themeMode])

  return chartRef
}
