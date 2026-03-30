import { useEffect, useRef, useMemo } from 'react'
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
import type { BacktestTrade } from '../../api/backtest-api'

interface TradingChartProps {
  exchange: string
  symbol: string
  interval: Interval
  indicators: IndicatorConfig
  trades?: BacktestTrade[]
}

export function TradingChart({ exchange, symbol, interval, indicators, trades }: TradingChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useChart(containerRef)
  const { data, error, isLoading } = useOHLCV(exchange, symbol, interval)
  const indicatorData = useIndicators(data?.candles, indicators)

  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const indicatorRefs = useRef<IndicatorSeriesRefs | null>(null)
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null)

  // Main candlestick + volume series
  useEffect(() => {
    const chart = chartRef.current
    if (!chart || !data) return

    if (markersRef.current) {
      markersRef.current.detach()
      markersRef.current = null
    }
    if (candleRef.current) {
      chart.removeSeries(candleRef.current)
      candleRef.current = null
    }
    if (volumeRef.current) {
      chart.removeSeries(volumeRef.current)
      volumeRef.current = null
    }
    if (indicatorRefs.current) {
      removeIndicatorSeries(chart, indicatorRefs.current)
      indicatorRefs.current = null
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

    return () => {
      if (chart) {
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
      if (chart && indicatorRefs.current) {
        removeIndicatorSeries(chart, indicatorRefs.current)
        indicatorRefs.current = null
      }
    }
  }, [indicatorData, indicators]) // eslint-disable-line react-hooks/exhaustive-deps

  // Strategy backtest markers
  const markers = useMemo<SeriesMarker<Time>[]>(() => {
    if (!trades || trades.length === 0) return []
    return trades
      .map((t) => {
        const isBuy = t.side === 'BUY'
        const pnlStr = t.pnl !== 0 ? ` P&L:${t.pnl > 0 ? '+' : ''}${t.pnl.toFixed(2)}` : ''
        return {
          time: toUTCTimestamp(t.timestamp) as Time,
          position: (isBuy ? 'belowBar' : 'aboveBar') as 'belowBar' | 'aboveBar',
          color: isBuy ? '#2196F3' : '#FF9800',
          shape: (isBuy ? 'arrowUp' : 'arrowDown') as 'arrowUp' | 'arrowDown',
          text: `${isBuy ? 'BUY' : 'SELL'} ${t.quantity.toFixed(4)} @ ${t.price.toFixed(2)}${pnlStr}`,
        }
      })
      .sort((a, b) => (a.time as number) - (b.time as number))
  }, [trades])

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

  return (
    <div style={{ width: '100%', height: '100%', minHeight: 0, position: 'relative' }}>
      <div
        ref={containerRef}
        style={{ width: '100%', height: '100%' }}
      />
      {isLoading && <div className="chart-overlay">Loading...</div>}
      {error && <div className="chart-overlay chart-error">Failed to load data</div>}
    </div>
  )
}
