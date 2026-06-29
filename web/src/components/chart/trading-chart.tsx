import { useEffect, useRef, useMemo, useState } from 'react'
import {
  CandlestickSeries,
  HistogramSeries,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
  type ISeriesMarkersPluginApi,
} from 'lightweight-charts'
import { useChart } from './use-chart'
import { useOHLCV } from '../../hooks/use-ohlcv'
import { useIndicators } from '../../hooks/use-indicators'
import {
  addIndicatorSeries,
  removeIndicatorSeries,
  type IndicatorSeriesRefs,
} from './indicator-series'
import { useRealtimeBar } from '../../hooks/use-realtime-bar'
import { engulfingMarkers } from '../../lib/indicators/engulfing'
import { toUTCTimestamp } from '../../api/market-data-api'
import type { Interval, IndicatorConfig } from '../../types/market-data'
import type { BacktestPosition } from '../../api/backtest-api'
import { PositionBoxPrimitive, type PositionData } from './position-box-primitive'
import { useTimezone } from '../../lib/use-timezone'
import { useTheme } from '../../lib/use-theme'
import { readChartColors } from '../../lib/theme-colors'
import { makeChartTimeFormatter, type TimezoneMode } from '../../lib/datetime'

interface TradingChartProps {
  /** Composite symbol string: "{CODE}:{EXCHANGE}" e.g. "BTCUSDT:BINANCE" */
  symbol: string
  interval: Interval
  indicators: IndicatorConfig
  positions?: BacktestPosition[]
  highlightedPositionIndex?: number | null
  hoveredPositionIndex?: number | null
  onChartReady?: (chart: IChartApi) => void
}

export function TradingChart({
  symbol,
  interval,
  indicators,
  positions,
  highlightedPositionIndex = null,
  hoveredPositionIndex = null,
  onChartReady,
}: TradingChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const { mode } = useTimezone()
  const { mode: themeMode } = useTheme()
  const chartRef = useChart(containerRef, undefined, mode, themeMode)
  const { data, error, isLoading } = useOHLCV(symbol, interval)
  const indicatorData = useIndicators(data?.candles, indicators)

  // Ref pattern: subscribed crosshair handler reads fresh mode without resubscribing.
  const modeRef = useRef<TimezoneMode>(mode)
  useEffect(() => { modeRef.current = mode }, [mode])

  // Live-update legend timestamp when mode flips (ohlcv state may already hold a
  // formatted string from previous mode — reformat from the current hovered time).
  const hoveredTimeRef = useRef<number | null>(null)

  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const [ohlcv, setOhlcv] = useState<{ o: number; h: number; l: number; c: number; v: number; t: string } | null>(null)
  const indicatorRefs = useRef<IndicatorSeriesRefs | null>(null)
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null)
  const boxPrimitiveRef = useRef<PositionBoxPrimitive | null>(null)

  // Notify parent when chart is ready (after useChart effect has run)
  useEffect(() => {
    const chart = chartRef.current
    if (chart && onChartReady) onChartReady(chart)
  }, [onChartReady])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart || !data) return

    // Clear stale refs — series may belong to a previous (destroyed) chart instance
    // after route navigation, so removeSeries can throw. Best-effort cleanup.
    try {
      if (markersRef.current) { markersRef.current.detach(); markersRef.current = null }
      if (candleRef.current) { chart.removeSeries(candleRef.current); candleRef.current = null }
      if (volumeRef.current) { chart.removeSeries(volumeRef.current); volumeRef.current = null }
      if (indicatorRefs.current) { removeIndicatorSeries(chart, indicatorRefs.current); indicatorRefs.current = null }
    } catch {
      candleRef.current = null
      volumeRef.current = null
      indicatorRefs.current = null
      markersRef.current = null
    }

    const cc = readChartColors()
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: cc.up,
      downColor: cc.down,
      borderVisible: false,
      wickUpColor: cc.up,
      wickDownColor: cc.down,
    })
    candleSeries.setData(data.candles)
    candleRef.current = candleSeries

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    })
    volumeSeries.setData(data.volumes)
    volumeRef.current = volumeSeries

    // Show ~80 bars at a usable zoom with the latest bar centered — leaves
    // empty space on the right so live candles have room to grow into the
    // viewport (standard trading UX). Users can scroll left for older data.
    const VISIBLE_BARS = 80
    const HALF = Math.floor(VISIBLE_BARS / 2)
    const total = data.candles.length
    if (total > 0) {
      const lastIdx = total - 1
      chart.timeScale().setVisibleLogicalRange({
        from: lastIdx - HALF,
        to: lastIdx + HALF,
      })
    }

    chart.subscribeCrosshairMove((param) => {
      if (!param.time || !param.seriesData) {
        hoveredTimeRef.current = null
        setOhlcv(null)
        return
      }
      const candle = param.seriesData.get(candleSeries) as { open: number; high: number; low: number; close: number } | undefined
      const vol = param.seriesData.get(volumeSeries) as { value: number } | undefined
      if (candle) {
        const t = param.time as number
        hoveredTimeRef.current = t
        const text = makeChartTimeFormatter(modeRef.current)(t)
        setOhlcv({ o: candle.open, h: candle.high, l: candle.low, c: candle.close, v: vol?.value ?? 0, t: text })
      } else {
        hoveredTimeRef.current = null
        setOhlcv(null)
      }
    })

    return () => {
      if (chartRef.current) {
        if (candleRef.current) {
          chart.removeSeries(candleRef.current)
          candleRef.current = null
        }
        if (volumeRef.current) {
          chart.removeSeries(volumeRef.current)
          volumeRef.current = null
        }
      }
    }
  }, [data]) // eslint-disable-line react-hooks/exhaustive-deps

  useRealtimeBar(symbol, interval, candleRef, volumeRef)

  // Reformat parked legend timestamp on mode toggle (crosshair handler only
  // fires on movement — without this, a stationary crosshair stays in old tz).
  useEffect(() => {
    const t = hoveredTimeRef.current
    if (t == null) return
    const text = makeChartTimeFormatter(mode)(t)
    setOhlcv((prev) => (prev ? { ...prev, t: text } : prev))
  }, [mode])

  // Re-color candles on theme flip — series is created in the [data] effect, so
  // without this a toggle wouldn't update colors until data reloads.
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

  // Strategy backtest markers — deduplicated by candle timestamp to avoid stacking
  // when chart interval differs from backtest interval (e.g. 1H backtest on 4H chart)
  const markers = useMemo<SeriesMarker<Time>[]>(() => {
    if (!positions || positions.length === 0) return []

    // Count occurrences per (time, side) to aggregate duplicates
    const buyCount = new Map<number, number>()
    const sellCount = new Map<number, number>()

    for (const p of positions) {
      const t = toUTCTimestamp(p.entry_time)
      buyCount.set(t, (buyCount.get(t) ?? 0) + 1)
      if (p.exit_time != null && p.exit_price != null) {
        const t2 = toUTCTimestamp(p.exit_time)
        sellCount.set(t2, (sellCount.get(t2) ?? 0) + 1)
      }
    }

    const result: SeriesMarker<Time>[] = []
    for (const [t, n] of buyCount) {
      result.push({
        time: t as Time,
        position: 'belowBar',
        color: '#2196F3',
        shape: 'arrowUp',
        text: n > 1 ? `BUY ×${n}` : 'BUY',
      })
    }
    for (const [t, n] of sellCount) {
      result.push({
        time: t as Time,
        position: 'aboveBar',
        color: '#FF9800',
        shape: 'arrowDown',
        text: n > 1 ? `SELL ×${n}` : 'SELL',
      })
    }
    return result.sort((a, b) => (a.time as number) - (b.time as number))
  }, [positions])

  // Pattern markers from the engulfing toggle — independent of backtest positions.
  const engulfMarkers = useMemo<SeriesMarker<Time>[]>(() => {
    if (!indicators.engulfing || !data?.candles) return []
    return engulfingMarkers(data.candles)
  }, [indicators.engulfing, data])

  // One marker set drives one plugin instance: backtest + engulfing share the
  // candle series, so merge into a single sorted array before setMarkers — a
  // second createSeriesMarkers call would replace, not add.
  const mergedMarkers = useMemo<SeriesMarker<Time>[]>(
    () => [...markers, ...engulfMarkers].sort((a, b) => (a.time as number) - (b.time as number)),
    [markers, engulfMarkers],
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

    if (boxPrimitiveRef.current) {
      candle.detachPrimitive(boxPrimitiveRef.current)
      boxPrimitiveRef.current = null
    }

    if (!positions || positions.length === 0) return

    const lastCandleTime = data?.candles.at(-1)?.time ?? null

    const posData: PositionData[] = positions
      .map((p, idx): PositionData | null => {
        const x2 = p.exit_time != null
          ? toUTCTimestamp(p.exit_time) as Time
          : lastCandleTime as Time
        if (!x2) return null
        return {
          x1: toUTCTimestamp(p.entry_time) as Time,
          x2,
          entry_price: p.entry_price,
          exit_price: p.exit_price,
          sl_price: p.sl_price,
          tp_price: p.tp_price,
          quantity: p.quantity,
          pnl: p.pnl,
          commission: p.commission,
          direction: p.direction ?? 'LONG',
          index: idx,
        }
      })
      .filter((p): p is PositionData => p !== null)

    if (posData.length === 0) return

    const primitive = new PositionBoxPrimitive(posData, highlightedPositionIndex, hoveredPositionIndex)
    candle.attachPrimitive(primitive)
    boxPrimitiveRef.current = primitive

    return () => {
      if (candleRef.current && boxPrimitiveRef.current) {
        candleRef.current.detachPrimitive(boxPrimitiveRef.current)
        boxPrimitiveRef.current = null
      }
    }
  }, [positions, data, highlightedPositionIndex, hoveredPositionIndex])

  return (
    <div style={{ width: '100%', height: '100%', minHeight: 0, position: 'relative' }}>
      <div
        ref={containerRef}
        style={{ width: '100%', height: '100%' }}
      />
      {ohlcv && (
        <div className="chart-ohlcv-legend">
          <span className="ohlcv-time">{ohlcv.t}</span>
          <span>O <b>{ohlcv.o.toFixed(2)}</b></span>
          <span>H <b>{ohlcv.h.toFixed(2)}</b></span>
          <span>L <b>{ohlcv.l.toFixed(2)}</b></span>
          <span>C <b style={{ color: ohlcv.c >= ohlcv.o ? 'var(--up-color)' : 'var(--down-color)' }}>{ohlcv.c.toFixed(2)}</b></span>
          <span>V <b>{ohlcv.v.toFixed(2)}</b></span>
        </div>
      )}
      {isLoading && <div className="chart-overlay">Loading...</div>}
      {error && <div className="chart-overlay chart-error">Failed to load data</div>}
    </div>
  )
}
