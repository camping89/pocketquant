/**
 * Embedded chart for the strategy operator dashboard.
 * Displays candles + live-trade markers + open-position price lines, plus the
 * shared indicator series (toggled by the parent) reused from the charts page.
 *
 * Intentionally has NO symbol/interval controls — those are locked to the
 * selected subscription's values.
 *
 * Architecture: wraps useChart + useOHLCV directly (not TradingChart) to avoid
 * pulling in backtest primitives (PositionBoxPrimitive) that are irrelevant
 * here. Indicator series are shared via indicator-series.ts (no duplicate logic).
 */
import { useEffect, useMemo, useRef } from 'react'
import {
  CandlestickSeries,
  HistogramSeries,
  createSeriesMarkers,
  LineStyle,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
  type IPriceLine,
} from 'lightweight-charts'
import { useChart } from '../chart/use-chart'
import { useOHLCV } from '../../hooks/use-ohlcv'
import { useIndicators } from '../../hooks/use-indicators'
import {
  addIndicatorSeries,
  removeIndicatorSeries,
  type IndicatorSeriesRefs,
} from '../chart/indicator-series'
import { engulfingMarkers } from '../../lib/indicators/engulfing'
import { tradesToMarkers } from '../../lib/trades-to-markers'
import { useTimezone } from '../../lib/use-timezone'
import { useTheme } from '../../lib/use-theme'
import { readChartColors } from '../../lib/theme-colors'
import type { Trade, OpenPosition } from '../../types/strategy'
import type { Interval, IndicatorConfig } from '../../types/market-data'

// TODO(realtime): wire useRealtimeBar(symbol, interval, candleRef, volumeRef)
// once the strategy WS subscription endpoint is available. Trades + open
// position also need their own WS channel — mark as future work.

interface StrategyChartProps {
  symbol: string
  interval: Interval
  trades: Trade[]
  openPosition: OpenPosition | null
  indicators: IndicatorConfig
}

export function StrategyChart({ symbol, interval, trades, openPosition, indicators }: StrategyChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const { mode } = useTimezone()
  const { mode: themeMode } = useTheme()
  const chartRef = useChart(containerRef, undefined, mode, themeMode)
  const { data, isLoading, error } = useOHLCV(symbol, interval)
  const indicatorData = useIndicators(data?.candles, indicators)

  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null)
  const indicatorRefs = useRef<IndicatorSeriesRefs | null>(null)
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
      if (indicatorRefs.current) { removeIndicatorSeries(chart, indicatorRefs.current); indicatorRefs.current = null }
    } catch {
      candleRef.current = null
      volumeRef.current = null
      markersRef.current = null
      indicatorRefs.current = null
    }

    const cc = readChartColors()
    const candle = chart.addSeries(CandlestickSeries, {
      upColor: cc.up,
      downColor: cc.down,
      borderVisible: false,
      wickUpColor: cc.up,
      wickDownColor: cc.down,
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

  // Re-color candles on theme flip — series is created in the [data] effect.
  useEffect(() => {
    const c = readChartColors()
    candleRef.current?.applyOptions({
      upColor: c.up,
      downColor: c.down,
      wickUpColor: c.up,
      wickDownColor: c.down,
    })
  }, [themeMode])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart || !indicatorData) return

    if (indicatorRefs.current) {
      removeIndicatorSeries(chart, indicatorRefs.current)
      indicatorRefs.current = null
    }

    indicatorRefs.current = addIndicatorSeries(chart, indicatorData, indicators)

    return () => {
      if (chartRef.current && indicatorRefs.current) {
        removeIndicatorSeries(chartRef.current, indicatorRefs.current)
        indicatorRefs.current = null
      }
    }
  }, [indicatorData, indicators]) // eslint-disable-line react-hooks/exhaustive-deps

  const tradeMarkers = useMemo<SeriesMarker<Time>[]>(
    () => tradesToMarkers(trades) as SeriesMarker<Time>[],
    [trades],
  )

  const engulfMarkers = useMemo<SeriesMarker<Time>[]>(() => {
    if (!indicators.engulfing || !data?.candles) return []
    return engulfingMarkers(data.candles)
  }, [indicators.engulfing, data])

  // One marker set drives one plugin instance: trade + engulfing share the
  // candle series, so merge into a single sorted array before setMarkers — a
  // second createSeriesMarkers call would replace, not add.
  const mergedMarkers = useMemo<SeriesMarker<Time>[]>(
    () => [...tradeMarkers, ...engulfMarkers].sort((a, b) => (a.time as number) - (b.time as number)),
    [tradeMarkers, engulfMarkers],
  )

  useEffect(() => {
    if (!candleRef.current) return

    if (markersRef.current) {
      markersRef.current.setMarkers(mergedMarkers)
    } else if (mergedMarkers.length > 0) {
      markersRef.current = createSeriesMarkers(candleRef.current, mergedMarkers)
    }
  }, [mergedMarkers])

  // Detach the markers plugin only on unmount — toggling to an empty set clears
  // markers via setMarkers([]) above, so detaching on empty would churn the
  // plugin and flicker when markers return.
  useEffect(() => {
    return () => {
      if (markersRef.current) {
        markersRef.current.detach()
        markersRef.current = null
      }
    }
  }, [])

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
  }, [openPosition])

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
            background: 'color-mix(in srgb, var(--bg-primary) 60%, transparent)',
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
