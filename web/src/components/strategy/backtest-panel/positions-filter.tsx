import type { FilterKey } from './positions-utils'

interface PositionsFilterProps {
  filter: FilterKey
  onChange: (filter: FilterKey) => void
  /** Active-filter total from the server; other chips show no count (a single
   *  paged query can't know every filter's size without extra round-trips). */
  activeCount: number
}

const CHIPS: { id: FilterKey; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'wins', label: 'Wins' },
  { id: 'losses', label: 'Losses' },
]

export function PositionsFilter({ filter, onChange, activeCount }: PositionsFilterProps) {
  return (
    <div className="positions-filter">
      {CHIPS.map((chip) => (
        <button
          key={chip.id}
          type="button"
          className={`positions-filter__chip${filter === chip.id ? ' positions-filter__chip--active' : ''}`}
          onClick={() => onChange(chip.id)}
        >
          {chip.label}
          {filter === chip.id && <span className="positions-filter__count">{activeCount}</span>}
        </button>
      ))}
    </div>
  )
}
