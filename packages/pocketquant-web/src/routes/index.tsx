import { useState, useMemo, useEffect } from 'react'
import { createFileRoute, getRouteApi } from '@tanstack/react-router'
import { AppHeader } from '../components/layout/app-header'
import { TradingChart } from '../components/chart/trading-chart'
import { SubscriptionPanel } from '../components/strategy/subscription-panel'
import { useAvailableIntervals } from '../hooks/use-available-intervals'
import { useOHLCV } from '../hooks/use-ohlcv'
import { useSubscriptionBacktest } from '../hooks/use-subscriptions'
import type { Interval, IndicatorConfig } from '../types/market-data'
import type { BacktestPosition } from '../api/backtest-api'

export const Route = createFileRoute('/')({
  component: ChartPage,
})

const rootApi = getRouteApi('__root__')

const DEFAULT_INTERVAL: Interval = '1d'
const DEFAULT_INDICATORS: IndicatorConfig = {
  sma: false,
  ema: false,
  rsi: false,
  macd: false,
  bollinger: false,
}

function ChartPage() {
  const { exchange, symbol } = rootApi.useSearch()
  const [selectedInterval, setSelectedInterval] = useState<Interval>(DEFAULT_INTERVAL)
  const [indicators, setIndicators] = useState<IndicatorConfig>(DEFAULT_INDICATORS)
  const [selectedStrategy, setSelectedStrategy] = useState<string | null>(null)
  const [selectedSubId, setSelectedSubId] = useState<string | null>(null)
  const availableIntervals = useAvailableIntervals({ exchange, symbol })

  const { data: ohlcvData } = useOHLCV(exchange, symbol, selectedInterval)

  // Reset selected sub whenever strategy changes
  useEffect(() => {
    setSelectedSubId(null)
  }, [selectedStrategy])

  const { data: backtestDoc } = useSubscriptionBacktest(selectedStrategy, selectedSubId)

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

  // Only pass positions when backtest is completed
  const positions = backtestDoc?.status === 'completed'
    ? (backtestDoc.positions as BacktestPosition[] | undefined)
    : undefined

  return (
    <div className="app-layout">
      <AppHeader
        intervals={availableIntervals}
        interval={interval}
        onIntervalChange={setSelectedInterval}
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
          <TradingChart
            exchange={exchange}
            symbol={symbol}
            interval={interval}
            indicators={indicators}
            positions={positions}
          />
        </main>
      </div>
    </div>
  )
}
