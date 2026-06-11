import type { IndicatorConfig } from '../../types/market-data'

const INDICATORS: { key: keyof IndicatorConfig; label: string; color: string }[] = [
  { key: 'sma', label: 'SMA', color: '#2196F3' },
  { key: 'ema', label: 'EMA', color: '#FF9800' },
  { key: 'rsi', label: 'RSI', color: '#AB47BC' },
  { key: 'macd', label: 'MACD', color: '#26C6DA' },
  { key: 'bollinger', label: 'BB', color: '#2196F3' },
]

interface IndicatorTogglesProps {
  value: IndicatorConfig
  onChange: (v: IndicatorConfig) => void
}

export function IndicatorToggles({ value, onChange }: IndicatorTogglesProps) {
  return (
    <div className="indicator-group">
      {INDICATORS.map((ind) => (
        <button
          key={ind.key}
          className={`indicator-btn ${value[ind.key] ? 'active' : ''}`}
          style={value[ind.key] ? { borderColor: ind.color, color: ind.color } : undefined}
          onClick={() => onChange({ ...value, [ind.key]: !value[ind.key] })}
        >
          {ind.label}
        </button>
      ))}
    </div>
  )
}
