import { useEffect, useRef, useMemo, useState } from 'react'
import {
  CandlestickSeries,
  HistogramSeries,
  createSeriesMarkers,
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
import { toUTCTimestamp } from '../../api/market-data-api'
import type { Interval, IndicatorConfig } from '../../types/market-data'
import type { BacktestPosition } from '../../api/backtest-api'
import { PositionBoxPrimitive, type PositionData } from './position-box-primitive'

interface TradingChartProps {
  exchange: string
  symbol: string
  interval: Interval
  indicators: IndicatorConfig
  positions?: BacktestPosition[]
}

export function TradingChart({ exchange, symbol, interval, indicators, positions }: TradingChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useChart(containerRef)
  const { data, error, isLoading } = useOHLCV(exchange, symbol, interval)
  const indicatorData = useIndicators(data?.candles, indicators)

  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const [ohlcv, setOhlcv] = useState<{ o: number; h: number; l: number; c: number; v: number; t: string } | null>(null)
  const indicatorRefs = useRef<IndicatorSeriesRefs | null>(null)
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null)
  const boxPrimitiveRef = useRef<PositionBoxPrimitive | null>(null)

  // Main candlestick + volume series
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

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
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

    chart.timeScale().fitContent()

    chart.subscribeCrosshairMove((param) => {
      if (!param.time || !param.seriesData) {
        setOhlcv(null)
        return
      }
      const candle = param.seriesData.get(candleSeries) as { open: number; high: number; low: number; close: number } | undefined
      const vol = param.seriesData.get(volumeSeries) as { value: number } | undefined
      if (candle) {
        const d = new Date((param.time as number) * 1000)
        const pad = (n: number) => String(n).padStart(2, '0')
        const t = `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`
        setOhlcv({ o: candle.open, h: candle.high, l: candle.low, c: candle.close, v: vol?.value ?? 0, t })
      } else {
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

  useRealtimeBar(exchange, symbol, interval, candleRef, volumeRef)

  // Indicator series
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

  useEffect(() => {
    if (!candleRef.current) return

    if (markersRef.current) {
      markersRef.current.setMarkers(markers)
    } else if (markers.length > 0) {
      markersRef.current = createSeriesMarkers(candleRef.current, markers)
    }

    return () => {
      if (markersRef.current && markers.length === 0) {
        markersRef.current.detach()
        markersRef.current = null
      }
    }
  }, [markers])

  // Position boxes — draws background, SL/TP lines with labels, entry line, and info text
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
      .map((p) => {
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
        } satisfies PositionData
      })
      .filter((p): p is PositionData => p !== null)

    if (posData.length === 0) return

    const primitive = new PositionBoxPrimitive(posData)
    candle.attachPrimitive(primitive)
    boxPrimitiveRef.current = primitive

    return () => {
      if (candleRef.current && boxPrimitiveRef.current) {
        candleRef.current.detachPrimitive(boxPrimitiveRef.current)
        boxPrimitiveRef.current = null
      }
    }
  }, [positions, data])

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
          <span>C <b style={{ color: ohlcv.c >= ohlcv.o ? '#26a69a' : '#ef5350' }}>{ohlcv.c.toFixed(2)}</b></span>
          <span>V <b>{ohlcv.v.toFixed(2)}</b></span>
        </div>
      )}
      {isLoading && <div className="chart-overlay">Loading...</div>}
      {error && <div className="chart-overlay chart-error">Failed to load data</div>}
    </div>
  )
}
