import { useEffect, useRef, type RefObject } from 'react'
import {
  createChart,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type DeepPartial,
  type ChartOptions,
} from 'lightweight-charts'

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
  localization: {
    // Display times in UTC regardless of browser timezone
    timeFormatter: (t: number) => {
      const d = new Date(t * 1000)
      const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
      const dd = String(d.getUTCDate()).padStart(2, '0')
      const hh = String(d.getUTCHours()).padStart(2, '0')
      const mi = String(d.getUTCMinutes()).padStart(2, '0')
      return `${d.getUTCFullYear()}-${mm}-${dd} ${hh}:${mi} UTC`
    },
  },
}

export function useChart(
  containerRef: RefObject<HTMLDivElement | null>,
  options?: DeepPartial<ChartOptions>,
) {
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const chart = createChart(el, { ...DEFAULT_OPTIONS, ...options })
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

  return chartRef
}
