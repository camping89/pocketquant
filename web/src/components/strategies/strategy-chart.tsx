/**
 * Embedded chart for the strategy operator dashboard.
 * Displays candles + live-trade markers + open-position price lines.
 *
 * Intentionally has NO symbol/interval/indicator controls — those are locked
 * to the selected subscription's values.
 *
 * Architecture: wraps useChart + useOHLCV directly (not TradingChart) to avoid
 * pulling in backtest primitives (PositionBoxPrimitive, indicator series, etc.)
 * that are irrelevant here.
 */
import { useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  HistogramSeries,
  createSeriesMarkers,
  LineStyle,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type Time,
  type IPriceLine,
} from 'lightweight-charts'
import { useChart } from '../chart/use-chart'
import { useOHLCV } from '../../hooks/use-ohlcv'
import { tradesToMarkers } from '../../lib/trades-to-markers'
import { useTimezone } from '../../lib/use-timezone'
import type { Trade, OpenPosition } from '../../types/strategy'
import type { Interval } from '../../types/market-data'

// TODO(realtime): wire useRealtimeBar(symbol, interval, candleRef, volumeRef)
// once the strategy WS subscription endpoint is available. Trades + open
// position also need their own WS channel — mark as future work.

interface StrategyChartProps {
  symbol: string
  interval: Interval
  trades: Trade[]
  openPosition: OpenPosition | null
}

export function StrategyChart({ symbol, interval, trades, openPosition }: StrategyChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const { mode } = useTimezone()
  const chartRef = useChart(containerRef, undefined, mode)
  const { data, isLoading, error } = useOHLCV(symbol, interval)

  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null)
  const entryLineRef = useRef<IPriceLine | null>(null)
  const liqLineRef = useRef<IPriceLine | null>(null)

  useEffect(() => {
    const chart = chartRef.current
    if (!chart || !data) return

    // Tear down stale series safely (chart may have remounted)
    try {
      if (markersRef.current) { markersRef.current.detach(); markersRef.current = null }
      if (candleRef.current) { chart.removeSeries(candleRef.current); candleRef.current = null }
      if (volumeRef.current) { chart.removeSeries(volumeRef.current); volumeRef.current = null }
    } catch {
      candleRef.current = null
      volumeRef.current = null
      markersRef.current = null
    }

    const candle = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    })
    candle.setData(data.candles)
    candleRef.current = candle

    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })
    chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } })
    volume.setData(data.volumes)
    volumeRef.current = volume

    // Show last 80 bars centered on most recent candle
    const VISIBLE = 80
    const total = data.candles.length
    if (total > 0) {
      chart.timeScale().setVisibleLogicalRange({
        from: total - 1 - Math.floor(VISIBLE / 2),
        to: total - 1 + Math.floor(VISIBLE / 2),
      })
    }

    return () => {
      try {
        if (markersRef.current) { markersRef.current.detach(); markersRef.current = null }
        if (chart && candleRef.current) { chart.removeSeries(candleRef.current); candleRef.current = null }
        if (chart && volumeRef.current) { chart.removeSeries(volumeRef.current); volumeRef.current = null }
      } catch { /* chart may already be destroyed on unmount */ }
    }
  }, [data]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const candle = candleRef.current
    if (!candle) return

    const markers = tradesToMarkers(trades)

    if (markersRef.current) {
      markersRef.current.setMarkers(markers)
    } else if (markers.length > 0) {
      markersRef.current = createSeriesMarkers(candle, markers)
    }

    return () => {
      if (markersRef.current && markers.length === 0) {
        markersRef.current.detach()
        markersRef.current = null
      }
    }
  }, [trades]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const candle = candleRef.current
    if (!candle) return

    try {
      if (entryLineRef.current) { candle.removePriceLine(entryLineRef.current); entryLineRef.current = null }
      if (liqLineRef.current) { candle.removePriceLine(liqLineRef.current); liqLineRef.current = null }
    } catch { /* series may have been replaced */ }

    if (!openPosition) return

    const { side, entry_price, liq_price, leverage, qty } = openPosition
    const entryColor = side === 'long' ? '#10b981' : '#f43f5e'
    const sideLabel = side === 'long' ? 'LONG' : 'SHORT'
    const levStr = leverage > 1 ? `×${leverage}` : ''

    entryLineRef.current = candle.createPriceLine({
      price: entry_price,
      color: entryColor,
      lineWidth: 1,
      lineStyle: LineStyle.Solid,
      axisLabelVisible: true,
      title: `${sideLabel}${levStr} @ ${entry_price} (qty ${qty})`,
    })

    if (liq_price != null) {
      liqLineRef.current = candle.createPriceLine({
        price: liq_price,
        color: '#dc2626',
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: `Liq @ ${liq_price}`,
      })
    }

    return () => {
      try {
        if (candleRef.current && entryLineRef.current) {
          candleRef.current.removePriceLine(entryLineRef.current)
          entryLineRef.current = null
        }
        if (candleRef.current && liqLineRef.current) {
          candleRef.current.removePriceLine(liqLineRef.current)
          liqLineRef.current = null
        }
      } catch { /* ignore */ }
    }
  }, [openPosition]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      {/* Chart canvas — useChart + ResizeObserver fills this container */}
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />

      {isLoading && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'rgba(15,15,30,0.6)',
            color: 'var(--text-secondary)',
            fontSize: 12,
            pointerEvents: 'none',
          }}
        >
          Loading chart…
        </div>
      )}

      {error && !isLoading && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--down-color)',
            fontSize: 12,
            pointerEvents: 'none',
          }}
        >
          Failed to load chart data.
        </div>
      )}
    </div>
  )
}
