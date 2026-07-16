import type { Interval } from '../../types/market-data'
import type { IntervalOption } from '../../hooks/use-available-intervals'

interface IntervalSelectorProps {
  intervals: IntervalOption[]
  value: Interval
  onChange: (v: Interval) => void
}

export function IntervalSelector({ intervals, value, onChange }: IntervalSelectorProps) {
  if (intervals.length === 0) return null

  return (
    <div className="interval-group">
      {intervals.map((iv) => {
        const disabled = !iv.available
        const btn = (
          <button type="button"
            key={iv.value}
            className={`interval-btn ${value === iv.value ? 'active' : ''} ${disabled ? 'disabled' : ''}`}
            onClick={() => { if (!disabled) onChange(iv.value) }}
            disabled={disabled}
            aria-disabled={disabled}
          >
            {iv.label}
          </button>
        )

        if (!disabled) return btn

        return (
          <span
            key={iv.value}
            title="No data synced for this timeframe"
            style={{ display: 'inline-block', cursor: 'not-allowed' }}
          >
            {btn}
          </span>
        )
      })}
    </div>
  )
}
