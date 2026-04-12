import { useState, useMemo, useEffect } from 'react'
import { createFileRoute, getRouteApi } from '@tanstack/react-router'
import { AppHeader } from '../components/layout/app-header'
import { TradingChart } from '../components/chart/trading-chart'
import { useAvailableIntervals } from '../hooks/use-available-intervals'
import { useOHLCV } from '../hooks/use-ohlcv'
import { useBacktest } from '../hooks/use-backtest'
import type { Interval, IndicatorConfig } from '../types/market-data'

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
  const availableIntervals = useAvailableIntervals({ exchange, symbol })

  const { data: ohlcvData } = useOHLCV(exchange, symbol, selectedInterval)
  const backtest = useBacktest(exchange, symbol, selectedInterval)
  const isDebug = typeof window !== 'undefined' && localStorage.getItem('pq:debug') === '1'

  useEffect(() => {
    if (selectedStrategy) {
      backtest.run(selectedStrategy)
    } else {
      backtest.reset()
    }
  }, [selectedStrategy, exchange, symbol, selectedInterval]) // eslint-disable-line react-hooks/exhaustive-deps

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
        backtestLoading={backtest.isLoading}
        debugBarInfo={debugBarInfo}
      />
      <main className="chart-container">
        <TradingChart
          exchange={exchange}
          symbol={symbol}
          interval={interval}
          indicators={indicators}
          positions={backtest.data?.positions}
        />
      </main>
    </div>
  )
}
