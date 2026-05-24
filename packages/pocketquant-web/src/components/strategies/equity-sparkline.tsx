/**
 * Tiny equity curve sparkline using lightweight-charts.
 * 60px height, no axes, no legend — pure visual trend indicator.
 */
import { useEffect, useRef } from 'react'
import { createChart, type IChartApi, type ISeriesApi, type LineData } from 'lightweight-charts'
import type { EquityPoint } from '../../api/backtest-api'

interface EquitySparklineProps {
  equityCurve: EquityPoint[]
  /** Width in px; defaults to container width */
  width?: number
}

export function EquitySparkline({ equityCurve, width = 340 }: EquitySparklineProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      width,
      height: 60,
      layout: {
        background: { color: 'transparent' },
        textColor: 'transparent',
      },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
      crosshair: { horzLine: { visible: false }, vertLine: { visible: false } },
      rightPriceScale: { visible: false },
      leftPriceScale: { visible: false },
      timeScale: { visible: false, borderVisible: false },
      handleScroll: false,
      handleScale: false,
    })

    const series = chart.addLineSeries({
      color: '#26a69a',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    })

    chartRef.current = chart
    seriesRef.current = series

    return () => {
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [width])

  useEffect(() => {
    if (!seriesRef.current || equityCurve.length === 0) return
    const data: LineData[] = equityCurve.map((pt) => ({
      // lightweight-charts expects unix timestamp in seconds
      time: (new Date(pt.timestamp).getTime() / 1000) as LineData['time'],
      value: pt.equity,
    }))
    seriesRef.current.setData(data)
    chartRef.current?.timeScale().fitContent()
  }, [equityCurve])

  if (equityCurve.length === 0) {
    return (
      <div style={{ height: 60, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>No equity data</span>
      </div>
    )
  }

  return <div ref={containerRef} style={{ height: 60, width }} />
}
