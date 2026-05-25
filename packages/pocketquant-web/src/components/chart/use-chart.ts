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

const DEFAULT_OPTIONS: DeepPartial<ChartOptions> = {
  layout: {
    background: { type: ColorType.Solid, color: '#1a1a2e' },
    textColor: '#d1d4dc',
  },
  grid: {
    vertLines: { color: '#2B2B43' },
    horzLines: { color: '#2B2B43' },
  },
  crosshair: { mode: CrosshairMode.Normal },
  rightPriceScale: { borderColor: '#2B2B43' },
  timeScale: { borderColor: '#2B2B43', timeVisible: true },
}

export function useChart(
  containerRef: RefObject<HTMLDivElement | null>,
  options?: DeepPartial<ChartOptions>,
  mode: TimezoneMode = 'utc',
) {
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const initFormatter = makeChartTimeFormatter(mode)
    const chart = createChart(el, {
      ...DEFAULT_OPTIONS,
      ...options,
      localization: {
        ...DEFAULT_OPTIONS.localization,
        ...options?.localization,
        timeFormatter: initFormatter,
      },
      timeScale: {
        ...DEFAULT_OPTIONS.timeScale,
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

  return chartRef
}
