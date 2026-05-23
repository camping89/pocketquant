/* eslint-disable react-refresh/only-export-components -- TanStack Router requires Route export alongside components */
import { useState, useMemo, useCallback } from 'react'
import { createFileRoute, getRouteApi } from '@tanstack/react-router'
import { AppHeader } from '../components/layout/app-header'
import { TradingChart } from '../components/chart/trading-chart'
import { TickerWidget } from '../components/ticker-widget'
import { useAvailableIntervals } from '../hooks/use-available-intervals'
import { useOHLCV } from '../hooks/use-ohlcv'
import type { Interval, IndicatorConfig } from '../types/market-data'

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

function localStorageKey(symbol: string): string {
  return `chart.interval.${symbol}`
}

function readPersistedInterval(symbol: string): Interval | null {
  try {
    return (localStorage.getItem(localStorageKey(symbol)) as Interval | null)
  } catch {
    return null
  }
}

function writePersistedInterval(symbol: string, interval: Interval): void {
  try {
    localStorage.setItem(localStorageKey(symbol), interval)
  } catch {
    // storage quota or private-mode — silently ignore
  }
}

interface ChartPageInnerProps {
  /** Composite symbol string: "{CODE}:{EXCHANGE}" e.g. "BTCUSDT:BINANCE" */
  symbol: string
}

// Inner component remounted on symbol change via key — cleanly resets all local state
function ChartPageInner({ symbol }: ChartPageInnerProps) {
  const [selectedInterval, setSelectedInterval] = useState<Interval>(
    () => readPersistedInterval(symbol) ?? DEFAULT_INTERVAL,
  )
  const [indicators, setIndicators] = useState<IndicatorConfig>(DEFAULT_INDICATORS)
  const availableIntervals = useAvailableIntervals(symbol)
  const { data: ohlcvData } = useOHLCV(symbol, selectedInterval)

  const handleIntervalChange = useCallback((iv: Interval) => {
    setSelectedInterval(iv)
    writePersistedInterval(symbol, iv)
  }, [symbol])

  const isDebug = typeof window !== 'undefined' && localStorage.getItem('pq:debug') === '1'

  const debugBarInfo = useMemo(() => {
    if (!isDebug || !ohlcvData?.lastBarRaw) return undefined
    const { id, datetime } = ohlcvData.lastBarRaw
    return `_id: ${id} | datetime: ${datetime}`
  }, [isDebug, ohlcvData])

  const interval = useMemo(() => {
    const available = availableIntervals.filter((iv) => iv.available)
    if (available.length === 0) return selectedInterval
    if (available.some((iv) => iv.value === selectedInterval)) return selectedInterval
    return available[0].value
  }, [availableIntervals, selectedInterval])

  return (
    <div className="app-layout">
      <AppHeader
        intervals={availableIntervals}
        interval={interval}
        onIntervalChange={handleIntervalChange}
        indicators={indicators}
        onIndicatorsChange={setIndicators}
        debugBarInfo={debugBarInfo}
      />
      <div style={{ display: 'flex', flex: 1, minHeight: 0, overflow: 'hidden' }}>
        <main className="chart-container">
          <div style={{ display: 'flex', alignItems: 'center', padding: '4px 8px', borderBottom: '1px solid rgba(255,255,255,0.06)', minHeight: 32 }}>
            <TickerWidget symbol={symbol} />
          </div>
          <div style={{ flex: 1, minHeight: 0 }}>
            <TradingChart
              symbol={symbol}
              interval={interval}
              indicators={indicators}
            />
          </div>
        </main>
      </div>
    </div>
  )
}

function ChartPage() {
  const { symbol } = rootApi.useSearch()
  // key={symbol} remounts ChartPageInner on symbol switch,
  // cleanly resetting selectedInterval to localStorage value for the new symbol
  return <ChartPageInner key={symbol} symbol={symbol} />
}
