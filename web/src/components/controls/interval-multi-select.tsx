import { ACTIVE_INTERVALS } from '../../constants/active-intervals'
import { sortIntervals } from '../../lib/intervals'

interface IntervalMultiSelectProps {
  value: string[]
  onChange: (v: string[]) => void
}

export function IntervalMultiSelect({ value, onChange }: IntervalMultiSelectProps) {
  const entry = value[0]

  function toggle(iv: string) {
    const next = value.includes(iv) ? value.filter((v) => v !== iv) : [...value, iv]
    onChange(sortIntervals(next))
  }

  return (
    <div>
      <div className="interval-group">
        {ACTIVE_INTERVALS.map((iv) => {
          const isEntry = iv === entry
          return (
            <button
              type="button"
              key={iv}
              className={`interval-btn ${value.includes(iv) ? 'active' : ''}`}
              onClick={() => toggle(iv)}
              title={isEntry ? 'entry interval' : undefined}
              style={isEntry ? { fontWeight: 700 } : undefined}
            >
              {iv}
            </button>
          )
        })}
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>
        Lowest first: {value.join(' ')} - the lowest is the entry interval.
      </div>
    </div>
  )
}
