import { useState, useMemo, useEffect } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppHeader } from './components/layout/app-header'
import { TradingChart } from './components/chart/trading-chart'
import { useAvailableIntervals } from './hooks/use-available-intervals'
import { useOHLCV } from './hooks/use-ohlcv'
import { useBacktest } from './hooks/use-backtest'
import type { SelectedSymbol, Interval, IndicatorConfig } from './types/market-data'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 2,
    },
  },
})

const DEFAULT_SYMBOL: SelectedSymbol = { exchange: 'BINANCE', symbol: 'BTCUSDT' }
const DEFAULT_INTERVAL: Interval = '1d'
const DEFAULT_INDICATORS: IndicatorConfig = {
  sma: false,
  ema: false,
  rsi: false,
  macd: false,
  bollinger: false,
}

function ChartApp() {
  const [symbol, setSymbol] = useState<SelectedSymbol>(DEFAULT_SYMBOL)
  const [selectedInterval, setSelectedInterval] = useState<Interval>(DEFAULT_INTERVAL)
  const [indicators, setIndicators] = useState<IndicatorConfig>(DEFAULT_INDICATORS)
  const [selectedStrategy, setSelectedStrategy] = useState<string | null>(null)
  const availableIntervals = useAvailableIntervals(symbol)

  const { data: ohlcvData } = useOHLCV(symbol.exchange, symbol.symbol, selectedInterval)
  const backtest = useBacktest(symbol.exchange, symbol.symbol, selectedInterval)
  const isDebug = typeof window !== 'undefined' && localStorage.getItem('pq:debug') === '1'

  // Run backtest when strategy selected
  useEffect(() => {
    if (selectedStrategy) {
      backtest.run(selectedStrategy)
    } else {
      backtest.reset()
    }
  }, [selectedStrategy, symbol, selectedInterval]) // eslint-disable-line react-hooks/exhaustive-deps

  const debugBarInfo = useMemo(() => {
    if (!isDebug || !ohlcvData?.lastBarRaw) return undefined
    const { id, datetime } = ohlcvData.lastBarRaw
    return `_id: ${id} | datetime: ${datetime}`
  }, [isDebug, ohlcvData])

  // If selected interval not in available list, fall back to first available
  const interval = useMemo(() => {
    if (availableIntervals.length === 0) return selectedInterval
    if (availableIntervals.some((iv) => iv.value === selectedInterval)) return selectedInterval
    return availableIntervals[0].value
  }, [availableIntervals, selectedInterval])

  return (
    <div className="app-layout">
      <AppHeader
        symbol={symbol}
        onSymbolChange={setSymbol}
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
          exchange={symbol.exchange}
          symbol={symbol.symbol}
          interval={interval}
          indicators={indicators}
          positions={backtest.data?.positions}
        />
      </main>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ChartApp />
    </QueryClientProvider>
  )
}
