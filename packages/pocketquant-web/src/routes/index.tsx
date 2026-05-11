/* eslint-disable react-refresh/only-export-components -- TanStack Router requires Route export alongside components */
import { useState, useMemo, useEffect, useCallback, useRef } from 'react'
import { createFileRoute, getRouteApi } from '@tanstack/react-router'
import type { IChartApi } from 'lightweight-charts'
import { AppHeader } from '../components/layout/app-header'
import { TradingChart } from '../components/chart/trading-chart'
import { SubscriptionPanel } from '../components/strategy/subscription-panel'
import { BacktestPanel } from '../components/strategy/backtest-panel'
import { TickerWidget } from '../components/ticker-widget'
import { useAvailableIntervals } from '../hooks/use-available-intervals'
import { useOHLCV } from '../hooks/use-ohlcv'
import { useSubscriptions, useSubscriptionBacktest } from '../hooks/use-subscriptions'
import { toUTCTimestamp } from '../api/market-data-api'
import type { Interval, IndicatorConfig } from '../types/market-data'
import type { BacktestPosition } from '../api/backtest-api'

export const Route = createFileRoute('/')({
  component: ChartPage,
})

const rootApi = getRouteApi('__root__')

const DEFAULT_INTERVAL: Interval = '5m'
const DEFAULT_INDICATORS: IndicatorConfig = {
  sma: false,
  ema: false,
  rsi: false,
  macd: false,
  bollinger: false,
}

function localStorageKey(exchange: string, symbol: string): string {
  return `chart.interval.${exchange}.${symbol}`
}

function readPersistedInterval(exchange: string, symbol: string): Interval | null {
  try {
    return (localStorage.getItem(localStorageKey(exchange, symbol)) as Interval | null)
  } catch {
    return null
  }
}

function writePersistedInterval(exchange: string, symbol: string, interval: Interval): void {
  try {
    localStorage.setItem(localStorageKey(exchange, symbol), interval)
  } catch {
    // storage quota or private-mode — silently ignore
  }
}

interface ChartPageInnerProps {
  exchange: string
  symbol: string
}

// Inner component remounted on symbol change via key — cleanly resets all local state
function ChartPageInner({ exchange, symbol }: ChartPageInnerProps) {
  const [selectedInterval, setSelectedInterval] = useState<Interval>(
    () => readPersistedInterval(exchange, symbol) ?? DEFAULT_INTERVAL,
  )
  const [indicators, setIndicators] = useState<IndicatorConfig>(DEFAULT_INDICATORS)
  const [selectedStrategy, setSelectedStrategy] = useState<string | null>(null)
  const [selectedSubId, setSelectedSubId] = useState<string | null>(null)
  const availableIntervals = useAvailableIntervals({ exchange, symbol })
  const { data: ohlcvData } = useOHLCV(exchange, symbol, selectedInterval)

  // Reset selected sub whenever strategy changes (pre-existing pattern)
  useEffect(() => {
    setSelectedSubId(null) // eslint-disable-line react-hooks/set-state-in-effect
  }, [selectedStrategy])

  const { data: backtestDoc } = useSubscriptionBacktest(selectedStrategy, selectedSubId)
  const { data: subscriptions } = useSubscriptions(selectedStrategy)

  const selectedSub = useMemo(
    () => subscriptions?.find((s) => s.id === selectedSubId) ?? null,
    [subscriptions, selectedSubId],
  )

  const symbolMismatch = !!(
    selectedSub &&
    (selectedSub.symbol !== symbol || selectedSub.exchange !== exchange)
  )

  const chartApiRef = useRef<IChartApi | null>(null)
  const [chartApi, setChartApi] = useState<IChartApi | null>(null)
  const [highlightedPos, setHighlightedPos] = useState<number | null>(null)
  const [hoveredPos, setHoveredPos] = useState<number | null>(null)

  // Reset highlight when subscription changes
  useEffect(() => {
    setHighlightedPos(null)
    setHoveredPos(null)
  }, [selectedSubId])

  const handleChartReady = useCallback((chart: IChartApi) => {
    chartApiRef.current = chart
    setChartApi(chart)
  }, [])

  const handlePositionClick = useCallback(
    (idx: number, position: BacktestPosition) => {
      setHighlightedPos(idx)
      const chart = chartApiRef.current
      if (!chart) return
      const entry = toUTCTimestamp(position.entry_time)
      const exit = position.exit_time
        ? toUTCTimestamp(position.exit_time)
        : entry + 60 * 60 // +1h fallback for open positions
      const padding = Math.max((exit - entry) * 0.2, 60 * 5)
      try {
        chart.timeScale().setVisibleRange({
          from: (entry - padding) as never,
          to: (exit + padding) as never,
        })
      } catch {
        // setVisibleRange can throw if data not loaded yet — ignore
      }
    },
    [],
  )

  const handlePositionHover = useCallback(
    (idx: number | null, _position: BacktestPosition | null) => {
      void _position
      setHoveredPos(idx)
    },
    [],
  )

  const handleIntervalChange = useCallback((iv: Interval) => {
    setSelectedInterval(iv)
    writePersistedInterval(exchange, symbol, iv)
  }, [exchange, symbol])

  const isDebug = typeof window !== 'undefined' && localStorage.getItem('pq:debug') === '1'

  const debugBarInfo = useMemo(() => {
    if (!isDebug || !ohlcvData?.lastBarRaw) return undefined
    const { id, datetime } = ohlcvData.lastBarRaw
    return `_id: ${id} | datetime: ${datetime}`
  }, [isDebug, ohlcvData])

  const interval = useMemo(() => {
    if (availableIntervals.length === 0) return selectedInterval
    if (availableIntervals.some((iv) => iv.value === selectedInterval)) return selectedInterval
    return availableIntervals[0].value
  }, [availableIntervals, selectedInterval])

  const positions = backtestDoc?.status === 'completed'
    ? (backtestDoc.positions as BacktestPosition[] | undefined)
    : undefined

  return (
    <div className="app-layout">
      <AppHeader
        intervals={availableIntervals}
        interval={interval}
        onIntervalChange={handleIntervalChange}
        indicators={indicators}
        onIndicatorsChange={setIndicators}
        selectedStrategy={selectedStrategy}
        onStrategyChange={setSelectedStrategy}
        debugBarInfo={debugBarInfo}
      />
      <div style={{ display: 'flex', flex: 1, minHeight: 0, overflow: 'hidden' }}>
        <SubscriptionPanel
          strategyId={selectedStrategy}
          selectedSubId={selectedSubId}
          onSelectSub={setSelectedSubId}
        />
        <main className="chart-container">
          <div style={{ display: 'flex', alignItems: 'center', padding: '4px 8px', borderBottom: '1px solid rgba(255,255,255,0.06)', minHeight: 32 }}>
            <TickerWidget exchange={exchange} symbol={symbol} />
          </div>
          <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            <div style={{ flex: 1, minHeight: 0 }}>
              <TradingChart
                exchange={exchange}
                symbol={symbol}
                interval={interval}
                indicators={indicators}
                positions={positions}
                highlightedPositionIndex={highlightedPos}
                hoveredPositionIndex={hoveredPos}
                onChartReady={handleChartReady}
              />
            </div>
            {selectedSubId && symbolMismatch && (
              <div className="symbol-mismatch-banner">
                Backtest panel hidden — switch chart to {selectedSub?.exchange}:{selectedSub?.symbol} to view its backtest.
              </div>
            )}
            {selectedSubId && !symbolMismatch && backtestDoc && (
              <BacktestPanel
                backtest={backtestDoc}
                chart={chartApi}
                highlightedPositionIndex={highlightedPos}
                onPositionClick={handlePositionClick}
                onPositionHover={handlePositionHover}
              />
            )}
          </div>
        </main>
      </div>
    </div>
  )
}

function ChartPage() {
  const { exchange, symbol } = rootApi.useSearch()
  // key={exchange:symbol} remounts ChartPageInner on symbol switch,
  // cleanly resetting selectedInterval to localStorage value for the new symbol
  return <ChartPageInner key={`${exchange}:${symbol}`} exchange={exchange} symbol={symbol} />
}
