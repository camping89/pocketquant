import { useRef, useEffect } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import {
  fmtDateTime,
  fmtDuration,
  fmtPnl,
  fmtPrice,
  type SortDir,
  type SortKey,
} from './positions-utils'
import type { TradeRow } from '../../../api/backtest-api'
import { useTimezone } from '../../../lib/use-timezone'
import { formatQty } from '../../../lib/number-format'

interface PositionsTableProps {
  rows: TradeRow[]
  sortKey: SortKey
  sortDir: SortDir
  highlightedTradeId: string | null
  onSortChange: (key: SortKey) => void
  onRowClick: (row: TradeRow) => void
  onRowMouseEnter?: (row: TradeRow) => void
  onRowMouseLeave?: () => void
  /** Called when the viewport nears the loaded tail — fetch the next page. */
  onReachEnd?: () => void
  isFetchingNextPage?: boolean
}

interface Col {
  key: SortKey
  label: string
  numeric?: boolean
}

// Server-sortable columns. The leading '#' is a display ordinal (not a stable
// key), so it is not sortable anymore.
const COLUMNS: Col[] = [
  { key: 'entry_time', label: 'Entry Time' },
  { key: 'direction', label: 'Dir' },
  { key: 'entry_price', label: 'Entry', numeric: true },
  { key: 'exit_price', label: 'Exit', numeric: true },
  { key: 'quantity', label: 'Qty', numeric: true },
  { key: 'duration_seconds', label: 'Duration', numeric: true },
  { key: 'pnl', label: 'PnL', numeric: true },
  { key: 'commission', label: 'Fee', numeric: true },
  { key: 'status', label: 'Status' },
]

const ROW_HEIGHT = 30
const OVERSCAN = 8

export function PositionsTable({
  rows,
  sortKey,
  sortDir,
  highlightedTradeId,
  onSortChange,
  onRowClick,
  onRowMouseEnter,
  onRowMouseLeave,
  onReachEnd,
  isFetchingNextPage,
}: PositionsTableProps) {
  const { mode } = useTimezone()
  const scrollRef = useRef<HTMLDivElement>(null)

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: OVERSCAN,
  })

  const virtualRows = virtualizer.getVirtualItems()

  // Prefetch the next page when the last rendered row nears the loaded tail.
  useEffect(() => {
    const last = virtualRows.at(-1)
    if (last && last.index >= rows.length - 1 - OVERSCAN) onReachEnd?.()
  }, [virtualRows, rows.length, onReachEnd])

  const totalSize = virtualizer.getTotalSize()
  const paddingTop = virtualRows.length > 0 ? virtualRows[0].start : 0
  const paddingBottom =
    virtualRows.length > 0 ? totalSize - virtualRows[virtualRows.length - 1].end : 0

  return (
    <div ref={scrollRef} className="positions-table__scroll">
      <table className="positions-table">
        <thead>
          <tr>
            <th className="positions-table__th positions-table__th--num">#</th>
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
          {paddingTop > 0 && (
            <tr aria-hidden style={{ height: paddingTop }}>
              <td colSpan={COLUMNS.length + 1} style={{ padding: 0, border: 0 }} />
            </tr>
          )}
          {virtualRows.map((vr) => {
            const t = rows[vr.index]
            const dir = t.direction
            const status = t.exit_time ? 'Closed' : 'Open'
            const highlighted = highlightedTradeId === t.trade_id
            return (
              <tr
                key={t.trade_id}
                className={`positions-table__row${highlighted ? ' positions-table__row--highlighted' : ''}`}
                style={{ height: ROW_HEIGHT }}
                onClick={() => onRowClick(t)}
                onMouseEnter={onRowMouseEnter ? () => onRowMouseEnter(t) : undefined}
                onMouseLeave={onRowMouseLeave}
              >
                <td className="positions-table__td--num">{vr.index + 1}</td>
                <td>{fmtDateTime(t.entry_time, mode)}</td>
                <td>
                  <span className={`direction-badge direction-badge--${dir.toLowerCase()}`}>{dir}</span>
                </td>
                <td className="positions-table__td--num">{fmtPrice(t.entry_price)}</td>
                <td className="positions-table__td--num">{fmtPrice(t.exit_price)}</td>
                <td className="positions-table__td--num">{formatQty(t.quantity)}</td>
                <td className="positions-table__td--num">{fmtDuration(t)}</td>
                <td className={`positions-table__td--num ${t.pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}`}>
                  {fmtPnl(t.pnl)}
                </td>
                <td className="positions-table__td--num">{t.commission.toFixed(4)}</td>
                <td>{status}</td>
              </tr>
            )
          })}
          {paddingBottom > 0 && (
            <tr aria-hidden style={{ height: paddingBottom }}>
              <td colSpan={COLUMNS.length + 1} style={{ padding: 0, border: 0 }} />
            </tr>
          )}
          {rows.length === 0 && (
            <tr>
              <td colSpan={COLUMNS.length + 1} className="positions-table__empty">
                No trades match this filter.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {isFetchingNextPage && <div className="positions-table__loading">Loading more…</div>}
    </div>
  )
}
