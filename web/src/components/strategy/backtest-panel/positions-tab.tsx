import { useMemo, useState } from 'react'
import type { TradeRow } from '../../../api/backtest-api'
import { useBacktestTrades } from '../../../hooks/use-backtest-run'
import { PositionsFilter } from './positions-filter'
import { PositionsTable } from './positions-table'
import { fmtPnl, type FilterKey, type SortDir, type SortKey } from './positions-utils'

interface PositionsTabProps {
  runId: string
  enabled: boolean
  highlightedTradeId: string | null
  onTradeClick?: (trade: TradeRow) => void
  onTradeHover?: (trade: TradeRow | null) => void
}

export function PositionsTab({
  runId,
  enabled,
  highlightedTradeId,
  onTradeClick,
  onTradeHover,
}: PositionsTabProps) {
  const [filter, setFilter] = useState<FilterKey>('all')
  const [sortKey, setSortKey] = useState<SortKey>('entry_time')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const query = useBacktestTrades(runId, { sortKey, sortDir, filter }, enabled)
  const pages = query.data?.pages
  const rows = useMemo<TradeRow[]>(() => pages?.flatMap((p) => p.items) ?? [], [pages])
  const total = pages?.[0]?.total ?? 0
  const totalPnl = pages?.[0]?.total_pnl ?? 0

  const onSortChange = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  if (query.isLoading) {
    return (
      <div className="backtest-panel__tab-content">
        <div className="empty-state">Loading trades…</div>
      </div>
    )
  }

  if (total === 0 && filter === 'all') {
    return (
      <div className="backtest-panel__tab-content">
        <div className="empty-state">No closed trades in this backtest.</div>
      </div>
    )
  }

  return (
    <div className="backtest-panel__tab-content positions-tab">
      <div className="positions-tab__toolbar">
        <PositionsFilter filter={filter} onChange={setFilter} activeCount={total} />
        <div className="positions-tab__footer">
          <span>{total} trades</span>
          <span>·</span>
          <span className={totalPnl >= 0 ? 'pnl-positive' : 'pnl-negative'}>
            Total PnL {fmtPnl(totalPnl)}
          </span>
        </div>
      </div>
      <div className="positions-tab__table-wrap">
        <PositionsTable
          rows={rows}
          sortKey={sortKey}
          sortDir={sortDir}
          highlightedTradeId={highlightedTradeId}
          onSortChange={onSortChange}
          onRowClick={(t) => onTradeClick?.(t)}
          onRowMouseEnter={onTradeHover ? (t) => onTradeHover(t) : undefined}
          onRowMouseLeave={onTradeHover ? () => onTradeHover(null) : undefined}
          onReachEnd={() => {
            if (query.hasNextPage && !query.isFetchingNextPage) query.fetchNextPage()
          }}
          isFetchingNextPage={query.isFetchingNextPage}
        />
      </div>
    </div>
  )
}
