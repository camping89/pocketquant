import { IntervalSelector } from '../controls/interval-selector'
import { IndicatorToggles } from '../controls/indicator-toggles'
import { SymbolSelector } from '../controls/symbol-selector'
import type { Interval, IndicatorConfig } from '../../types/market-data'
import type { IntervalOption } from '../../hooks/use-available-intervals'

interface AppHeaderProps {
  symbol: string
  onSymbolChange: (v: string) => void
  intervals: IntervalOption[]
  interval: Interval
  onIntervalChange: (v: Interval) => void
  indicators: IndicatorConfig
  onIndicatorsChange: (v: IndicatorConfig) => void
  debugBarInfo?: string
}

export function AppHeader({
  symbol, onSymbolChange,
  intervals, interval, onIntervalChange,
  indicators, onIndicatorsChange,
  debugBarInfo,
}: AppHeaderProps) {
  return (
    <header className="app-header">
      <SymbolSelector value={symbol} onChange={onSymbolChange} />
      <IntervalSelector intervals={intervals} value={interval} onChange={onIntervalChange} />
      {debugBarInfo && <span style={{ color: '#8b8b9a', fontSize: 11, marginLeft: 8 }}>{debugBarInfo}</span>}
      <div style={{ flex: 1 }} />
      <IndicatorToggles value={indicators} onChange={onIndicatorsChange} />
    </header>
  )
}
