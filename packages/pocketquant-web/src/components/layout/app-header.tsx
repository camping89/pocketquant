import { IntervalSelector } from '../controls/interval-selector'
import { IndicatorToggles } from '../controls/indicator-toggles'
import { StrategySelector } from '../controls/strategy-selector'
import type { Interval, IndicatorConfig } from '../../types/market-data'

interface IntervalOption {
  label: string
  value: Interval
}

interface AppHeaderProps {
  intervals: IntervalOption[]
  interval: Interval
  onIntervalChange: (v: Interval) => void
  indicators: IndicatorConfig
  onIndicatorsChange: (v: IndicatorConfig) => void
  selectedStrategy: string | null
  onStrategyChange: (v: string | null) => void
  backtestLoading?: boolean
  debugBarInfo?: string
}

export function AppHeader({
  intervals, interval, onIntervalChange,
  indicators, onIndicatorsChange,
  selectedStrategy, onStrategyChange, backtestLoading,
  debugBarInfo,
}: AppHeaderProps) {
  return (
    <header className="app-header">
      <IntervalSelector intervals={intervals} value={interval} onChange={onIntervalChange} />
      <StrategySelector value={selectedStrategy} onChange={onStrategyChange} isLoading={backtestLoading} />
      {debugBarInfo && <span style={{ color: '#8b8b9a', fontSize: 11, marginLeft: 8 }}>{debugBarInfo}</span>}
      <div style={{ flex: 1 }} />
      <IndicatorToggles value={indicators} onChange={onIndicatorsChange} />
    </header>
  )
}
