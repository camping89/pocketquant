import { useRef, useEffect } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import {
  fmtDateTime,
  fmtDuration,
  fmtPrice,
  type SortDir,
  type SortKey,
} from './positions-utils'
import type { TradeRow } from '../../../api/backtest-api'
import { useTimezone } from '../../../lib/use-timezone'
import { formatQty, formatUsd, formatUsdPrecise, formatUsdSigned } from '../../../lib/number-format'

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
  // Sortable columns carry a server sort key; derived columns (notional, net)
  // omit it and render as display-only headers (keyset paging can't sort them).
  key?: SortKey
  label: string
  numeric?: boolean
}

const COLUMNS: Col[] = [
  { key: 'entry_time', label: 'Entry Time' },
  { key: 'direction', label: 'Dir' },
  { key: 'entry_price', label: 'Entry', numeric: true },
  { key: 'exit_price', label: 'Exit', numeric: true },
  { key: 'quantity', label: 'Qty', numeric: true },
  { label: 'Entry $', numeric: true },
  { label: 'Exit $', numeric: true },
  { key: 'duration_seconds', label: 'Duration', numeric: true },
  { key: 'pnl', label: 'PnL', numeric: true },
  { label: 'Net', numeric: true },
  { key: 'commission', label: 'Fee', numeric: true },
  { key: 'status', label: 'Status' },
]

const ROW_HEIGHT = 30
const OVERSCAN = 8

// Nearest scrollable ancestor — the single-scrollbar layout scrolls an outer
// pane, not this container, so the tail sentinel must intersect against it.
function getScrollParent(el: HTMLElement | null): HTMLElement | null {
  let node = el?.parentElement ?? null
  while (node) {
    const oy = getComputedStyle(node).overflowY
    if (oy === 'auto' || oy === 'scroll') return node
    node = node.parentElement
  }
  return null
}

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
  const sentinelRef = useRef<HTMLDivElement>(null)

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: OVERSCAN,
  })

  const virtualRows = virtualizer.getVirtualItems()

  // Prefetch the next page only when the tail sentinel actually scrolls into
  // view. A render-window check fires immediately when the viewport is
  // unbounded (single-scrollbar layout), chain-loading every page on open.
  useEffect(() => {
    const sentinel = sentinelRef.current
    if (!sentinel || !onReachEnd) return
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) onReachEnd()
      },
      { root: getScrollParent(scrollRef.current), rootMargin: '0px 0px 300px 0px' },
    )
    io.observe(sentinel)
    return () => io.disconnect()
  }, [onReachEnd])

  const totalSize = virtualizer.getTotalSize()
  const paddingTop = virtualRows.length > 0 ? virtualRows[0].start : 0
  const paddingBottom =
    virtualRows.length > 0 ? totalSize - virtualRows[virtualRows.length - 1].end : 0

  return (
    <div ref={scrollRef} className="positions-table__scroll">
      <table className="positions-table">
        <thead>
          <tr>
            <th className="positions-table__th">Trade Id</th>
            {COLUMNS.map((col) => (
              <th
                key={col.label}
                className={`positions-table__th${col.numeric ? ' positions-table__th--num' : ''}`}
                onClick={col.key ? () => onSortChange(col.key!) : undefined}
              >
                {col.label}
                {col.key && sortKey === col.key && (
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
                <td className="positions-table__td--mono">{t.trade_id.slice(-5)}</td>
                <td>{fmtDateTime(t.entry_time, mode)}</td>
                <td>
                  <span className={`direction-badge direction-badge--${dir.toLowerCase()}`}>{dir}</span>
                </td>
                <td className="positions-table__td--num">{fmtPrice(t.entry_price)}</td>
                <td className="positions-table__td--num">{fmtPrice(t.exit_price)}</td>
                <td className="positions-table__td--num">{formatQty(t.quantity)}</td>
                <td className="positions-table__td--num">{formatUsd(t.quantity * t.entry_price)}</td>
                <td className="positions-table__td--num">{formatUsd(t.quantity * t.exit_price)}</td>
                <td className="positions-table__td--num">{fmtDuration(t)}</td>
                <td className={`positions-table__td--num ${t.pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}`}>
                  {formatUsdSigned(t.pnl)}
                </td>
                <td className={`positions-table__td--num ${t.pnl - t.commission >= 0 ? 'pnl-positive' : 'pnl-negative'}`}>
                  {formatUsdSigned(t.pnl - t.commission)}
                </td>
                <td className="positions-table__td--num">{formatUsdPrecise(t.commission)}</td>
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
      <div ref={sentinelRef} aria-hidden className="positions-table__sentinel" />
      {isFetchingNextPage && <div className="positions-table__loading">Loading more…</div>}
    </div>
  )
}
