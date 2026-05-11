import {
  fmtDateTime,
  fmtDuration,
  fmtPnl,
  fmtPrice,
  type IndexedPosition,
  type SortDir,
  type SortKey,
} from './positions-utils'

interface PositionsTableProps {
  rows: IndexedPosition[]
  sortKey: SortKey
  sortDir: SortDir
  highlightedIndex: number | null
  onSortChange: (key: SortKey) => void
  onRowClick: (item: IndexedPosition) => void
  onRowMouseEnter?: (item: IndexedPosition) => void
  onRowMouseLeave?: () => void
}

interface Col {
  key: SortKey
  label: string
  numeric?: boolean
}

const COLUMNS: Col[] = [
  { key: 'index', label: '#', numeric: true },
  { key: 'entry_time', label: 'Entry Time' },
  { key: 'direction', label: 'Dir' },
  { key: 'entry_price', label: 'Entry', numeric: true },
  { key: 'exit_price', label: 'Exit', numeric: true },
  { key: 'quantity', label: 'Qty', numeric: true },
  { key: 'duration', label: 'Duration', numeric: true },
  { key: 'pnl', label: 'PnL', numeric: true },
  { key: 'commission', label: 'Fee', numeric: true },
  { key: 'status', label: 'Status' },
]

export function PositionsTable({
  rows,
  sortKey,
  sortDir,
  highlightedIndex,
  onSortChange,
  onRowClick,
  onRowMouseEnter,
  onRowMouseLeave,
}: PositionsTableProps) {
  return (
    <table className="positions-table">
      <thead>
        <tr>
          {COLUMNS.map((col) => (
            <th
              key={col.key}
              className={`positions-table__th${col.numeric ? ' positions-table__th--num' : ''}`}
              onClick={() => onSortChange(col.key)}
            >
              {col.label}
              {sortKey === col.key && (
                <span className="positions-table__sort-arrow">{sortDir === 'asc' ? ' ▲' : ' ▼'}</span>
              )}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((item) => {
          const p = item.position
          const dir = p.direction ?? 'LONG'
          const status = p.exit_time ? 'Closed' : 'Open'
          const highlighted = highlightedIndex === item.index
          return (
            <tr
              key={item.index}
              className={`positions-table__row${highlighted ? ' positions-table__row--highlighted' : ''}`}
              onClick={() => onRowClick(item)}
              onMouseEnter={onRowMouseEnter ? () => onRowMouseEnter(item) : undefined}
              onMouseLeave={onRowMouseLeave}
            >
              <td className="positions-table__td--num">{item.index + 1}</td>
              <td>{fmtDateTime(p.entry_time)}</td>
              <td>
                <span className={`direction-badge direction-badge--${dir.toLowerCase()}`}>{dir}</span>
              </td>
              <td className="positions-table__td--num">{fmtPrice(p.entry_price)}</td>
              <td className="positions-table__td--num">{fmtPrice(p.exit_price)}</td>
              <td className="positions-table__td--num">{p.quantity}</td>
              <td className="positions-table__td--num">{fmtDuration(p)}</td>
              <td className={`positions-table__td--num ${p.pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}`}>
                {fmtPnl(p.pnl)}
              </td>
              <td className="positions-table__td--num">{p.commission.toFixed(4)}</td>
              <td>{status}</td>
            </tr>
          )
        })}
        {rows.length === 0 && (
          <tr>
            <td colSpan={COLUMNS.length} className="positions-table__empty">
              No positions match this filter.
            </td>
          </tr>
        )}
      </tbody>
    </table>
  )
}
