import { useEffect, useRef, useMemo, useState } from 'react'
import {
  CandlestickSeries,
  HistogramSeries,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
  type IRange,
  type ISeriesMarkersPluginApi,
} from 'lightweight-charts'
import { useChart } from './use-chart'
import { useOhlcvHistory } from '../../hooks/use-ohlcv-history'
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
import type { TradeMarker, TradeRow } from '../../api/backtest-api'
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
  /** Lite per-trade rows driving BUY/SELL arrows for every trade in the run. */
  markers?: TradeMarker[]
  /** The clicked / hovered trade objects — draw the detail box for these only.
   *  Passing the object (not an index) keeps the box correct across paging. */
  highlightedTrade?: TradeRow | null
  hoveredTrade?: TradeRow | null
  /** Anchor OHLCV to a past window end (backtest mode). When set, the chart loads
   *  history ending at this instant and runs no realtime stream. */
  anchorEndDate?: string
  onChartReady?: (chart: IChartApi) => void
}

export function TradingChart({
  symbol,
  interval,
  indicators,
  markers: tradeMarkers,
  highlightedTrade = null,
  hoveredTrade = null,
  anchorEndDate,
  onChartReady,
}: TradingChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const { mode } = useTimezone()
  const { mode: themeMode } = useTheme()
  const chartRef = useChart(containerRef, undefined, mode, themeMode)
  const { data, error, isLoading, loadOlder, isLoadingOlder, hasMore } = useOhlcvHistory(
    symbol,
    interval,
    anchorEndDate,
  )
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

  // Pagination view-preservation: fit the 80-bar window only on the first data
  // load per series; subsequent updates (older-page prepend, realtime rollover)
  // restore the saved time range so the viewport doesn't yank back to the latest
  // bar. Time-based (not index-based) range survives bars prepended to the left.
  const didInitialFitRef = useRef(false)
  const savedRangeRef = useRef<IRange<Time> | null>(null)
  const loadOlderRef = useRef(loadOlder)
  useEffect(() => { loadOlderRef.current = loadOlder }, [loadOlder])

  // Reset the initial-fit latch when the series identity changes so the new
  // symbol/interval gets its own 80-bar fit.
  useEffect(() => {
    didInitialFitRef.current = false
    savedRangeRef.current = null
  }, [symbol, interval])

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

    // First load: show ~80 bars with the latest bar centered, leaving empty
    // space on the right so live candles grow into the viewport (standard
    // trading UX). Re-running setData (older-page prepend, realtime rollover)
    // must NOT re-fit — restore the saved time range so the user's scroll
    // position holds. Time-based range survives left-side prepends.
    const total = data.candles.length
    if (!didInitialFitRef.current && total > 0) {
      const VISIBLE_BARS = 80
      const HALF = Math.floor(VISIBLE_BARS / 2)
      const lastIdx = total - 1
      chart.timeScale().setVisibleLogicalRange({
        from: lastIdx - HALF,
        to: lastIdx + HALF,
      })
      didInitialFitRef.current = true
    } else if (savedRangeRef.current) {
      chart.timeScale().setVisibleRange(savedRangeRef.current)
    }

    // Scroll-left pagination: when the left edge nears the oldest loaded bar,
    // fetch an older page. The handler also parks the current range so the
    // [data] effect can restore it after the prepend re-renders.
    const timeScale = chart.timeScale()
    const onRangeChange = (logicalRange: { from: number; to: number } | null) => {
      const vr = timeScale.getVisibleRange()
      if (vr) savedRangeRef.current = vr
      if (logicalRange && logicalRange.from < 50) loadOlderRef.current()
    }
    timeScale.subscribeVisibleLogicalRangeChange(onRangeChange)

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
      timeScale.unsubscribeVisibleLogicalRangeChange(onRangeChange)
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

  useRealtimeBar(symbol, interval, candleRef, volumeRef, anchorEndDate == null)

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
    if (!tradeMarkers || tradeMarkers.length === 0) return []

    // Count occurrences per (time, side) to aggregate duplicates
    const buyCount = new Map<number, number>()
    const sellCount = new Map<number, number>()

    for (const p of tradeMarkers) {
      const t = toUTCTimestamp(p.entry_time)
      buyCount.set(t, (buyCount.get(t) ?? 0) + 1)
      if (p.exit_time != null) {
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
  }, [tradeMarkers])

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

    const lastCandleTime = data?.candles.at(-1)?.time ?? null

    // Box is detail-on-demand: draw it only for the clicked (highlight) and
    // hovered trades. Markers still mark every trade; no selection draws no box,
    // keeping the chart readable when a run has hundreds of trades. A hovered
    // trade that is also the highlight collapses to a single (click) box.
    const boxes: PositionData[] = []
    const toBox = (t: TradeRow, kind: 'click' | 'hover'): PositionData | null => {
      const x2 = t.exit_time != null ? (toUTCTimestamp(t.exit_time) as Time) : (lastCandleTime as Time)
      if (!x2) return null
      return {
        x1: toUTCTimestamp(t.entry_time) as Time,
        x2,
        entry_price: t.entry_price,
        exit_price: t.exit_price,
        sl_price: t.sl_price,
        tp_price: t.tp_price,
        quantity: t.quantity,
        pnl: t.pnl,
        commission: t.commission,
        direction: t.direction,
        highlightKind: kind,
      }
    }

    if (highlightedTrade) {
      const b = toBox(highlightedTrade, 'click')
      if (b) boxes.push(b)
    }
    if (hoveredTrade && hoveredTrade.trade_id !== highlightedTrade?.trade_id) {
      const b = toBox(hoveredTrade, 'hover')
      if (b) boxes.push(b)
    }

    if (boxes.length === 0) return

    const primitive = new PositionBoxPrimitive(boxes)
    candle.attachPrimitive(primitive)
    boxPrimitiveRef.current = primitive

    return () => {
      if (candleRef.current && boxPrimitiveRef.current) {
        candleRef.current.detachPrimitive(boxPrimitiveRef.current)
        boxPrimitiveRef.current = null
      }
    }
  }, [data, highlightedTrade, hoveredTrade])

  // Scroll the clicked trade into view. Driven by highlight only — hover must not
  // move the viewport, or scanning the table with the mouse would jerk the chart.
  useEffect(() => {
    const chart = chartRef.current
    const candles = data?.candles
    if (!chart || !candles || candles.length === 0) return
    if (!highlightedTrade) return
    const p = highlightedTrade

    const firstT = candles[0].time as number
    const lastT = candles.at(-1)!.time as number
    const barDur = candles.length > 1
      ? (candles[1].time as number) - (candles[0].time as number)
      : 60
    const pad = barDur * 50

    const entryT = toUTCTimestamp(p.entry_time)
    const exitT = p.exit_time != null ? toUTCTimestamp(p.exit_time) : lastT
    const clamp = (t: number) => Math.max(firstT, Math.min(lastT, t))
    const from = clamp(entryT - pad)
    const to = clamp(exitT + pad)

    try {
      chart.timeScale().setVisibleRange({ from: from as Time, to: to as Time })
    } catch {
      // range can be rejected before the series has data — ignore
    }
  }, [highlightedTrade, data]) // eslint-disable-line react-hooks/exhaustive-deps

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
      {isLoadingOlder && <div className="chart-history-loading">Loading history…</div>}
      {!hasMore && <div className="chart-history-end">Start of history</div>}
      {error && <div className="chart-overlay chart-error">Failed to load data</div>}
    </div>
  )
}
