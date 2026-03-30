import type { Interval } from '../../types/market-data'

interface IntervalOption {
  label: string
  value: Interval
}

interface IntervalSelectorProps {
  intervals: IntervalOption[]
  value: Interval
  onChange: (v: Interval) => void
}

export function IntervalSelector({ intervals, value, onChange }: IntervalSelectorProps) {
  if (intervals.length === 0) return null

  return (
    <div className="interval-group">
      {intervals.map((iv) => (
        <button
          key={iv.value}
          className={`interval-btn ${value === iv.value ? 'active' : ''}`}
          onClick={() => onChange(iv.value)}
        >
          {iv.label}
        </button>
      ))}
    </div>
  )
}
