import type { FilterKey } from './positions-utils'

interface PositionsFilterProps {
  filter: FilterKey
  onChange: (filter: FilterKey) => void
  counts: Record<FilterKey, number>
}

const CHIPS: { id: FilterKey; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'wins', label: 'Wins' },
  { id: 'losses', label: 'Losses' },
  { id: 'open', label: 'Open' },
]

export function PositionsFilter({ filter, onChange, counts }: PositionsFilterProps) {
  return (
    <div className="positions-filter">
      {CHIPS.map((chip) => (
        <button
          key={chip.id}
          type="button"
          className={`positions-filter__chip${filter === chip.id ? ' positions-filter__chip--active' : ''}`}
          onClick={() => onChange(chip.id)}
        >
          {chip.label} <span className="positions-filter__count">{counts[chip.id]}</span>
        </button>
      ))}
    </div>
  )
}
