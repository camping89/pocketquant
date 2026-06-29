import { useMemo, useState } from 'react'
import type { BacktestPosition, BacktestRunResult } from '../../../api/backtest-api'
import { PositionsFilter } from './positions-filter'
import { PositionsTable } from './positions-table'
import {
  aggregatePnl,
  applyFilter,
  fmtPnl,
  sortPositions,
  type FilterKey,
  type IndexedPosition,
  type SortDir,
  type SortKey,
} from './positions-utils'

interface PositionsTabProps {
  backtest: BacktestRunResult
  highlightedIndex: number | null
  onPositionClick?: (index: number, position: BacktestPosition) => void
  onPositionHover?: (index: number | null, position: BacktestPosition | null) => void
}

export function PositionsTab({
  backtest,
  highlightedIndex,
  onPositionClick,
  onPositionHover,
}: PositionsTabProps) {
  const [filter, setFilter] = useState<FilterKey>('all')
  const [sortKey, setSortKey] = useState<SortKey>('entry_time')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const indexed = useMemo<IndexedPosition[]>(
    () => backtest.positions.map((position, index) => ({ index, position })),
    [backtest.positions],
  )

  const counts = useMemo(
    () => ({
      all: indexed.length,
      wins: applyFilter(indexed, 'wins').length,
      losses: applyFilter(indexed, 'losses').length,
      open: applyFilter(indexed, 'open').length,
    }),
    [indexed],
  )

  const filtered = useMemo(() => applyFilter(indexed, filter), [indexed, filter])
  const sorted = useMemo(() => sortPositions(filtered, sortKey, sortDir), [filtered, sortKey, sortDir])

  const totalPnl = useMemo(() => aggregatePnl(filtered), [filtered])

  const onSortChange = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  if (indexed.length === 0) {
    return (
      <div className="backtest-panel__tab-content">
        <div className="empty-state">No positions in this backtest.</div>
      </div>
    )
  }

  return (
    <div className="backtest-panel__tab-content positions-tab">
      <div className="positions-tab__toolbar">
        <PositionsFilter filter={filter} onChange={setFilter} counts={counts} />
        <div className="positions-tab__footer">
          <span>{filtered.length} positions</span>
          <span>·</span>
          <span className={totalPnl >= 0 ? 'pnl-positive' : 'pnl-negative'}>
            Total PnL {fmtPnl(totalPnl)}
          </span>
        </div>
      </div>
      <div className="positions-tab__table-wrap">
        <PositionsTable
          rows={sorted}
          sortKey={sortKey}
          sortDir={sortDir}
          highlightedIndex={highlightedIndex}
          onSortChange={onSortChange}
          onRowClick={(item) => onPositionClick?.(item.index, item.position)}
          onRowMouseEnter={
            onPositionHover ? (item) => onPositionHover(item.index, item.position) : undefined
          }
          onRowMouseLeave={onPositionHover ? () => onPositionHover(null, null) : undefined}
        />
      </div>
    </div>
  )
}
