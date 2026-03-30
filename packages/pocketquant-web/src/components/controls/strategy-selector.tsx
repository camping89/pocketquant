import { useStrategies } from '../../hooks/use-backtest'

interface StrategySelectorProps {
  value: string | null
  onChange: (v: string | null) => void
  isLoading?: boolean
}

export function StrategySelector({ value, onChange, isLoading }: StrategySelectorProps) {
  const { data: strategies } = useStrategies()

  return (
    <select
      className="strategy-select"
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value || null)}
      disabled={isLoading}
    >
      <option value="">Strategy</option>
      {strategies?.map((s) => (
        <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
      ))}
    </select>
  )
}
