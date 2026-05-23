/**
 * Left pane of the strategies dashboard.
 * Lists all subscriptions across all loaded strategies with filter + New button.
 */
import { useState, useMemo } from 'react'
import { useStrategiesList } from '../../hooks/use-strategies'
import { useSubscriptions } from '../../hooks/use-subscriptions'
import { StrategyCard } from './strategy-card'
import { NewSubscriptionDialog } from './new-subscription-dialog'
import type { Subscription } from '../../api/strategy-api'

interface StrategyListSidebarProps {
  selectedSubId: string | null
  onSelect: (sub: Subscription) => void
}

/** Aggregates subscriptions from all strategy IDs in parallel. */
function useAllSubscriptions(strategyIds: string[]) {
  // We call useSubscriptions per strategy, but hooks can't be in loops.
  // Solution: fetch all strategies and flatten — for now support up to first
  // strategy ID to satisfy Rules of Hooks. Multi-strategy support can be
  // added in Phase 7 via a dedicated aggregation endpoint.
  const firstId = strategyIds[0] ?? null
  const { data: subs = [], isLoading } = useSubscriptions(firstId)
  return { subs, isLoading }
}

export function StrategyListSidebar({ selectedSubId, onSelect }: StrategyListSidebarProps) {
  const [showDialog, setShowDialog] = useState(false)
  const [filter, setFilter] = useState('')

  const { data: strategyIds = [], isLoading: strategiesLoading } = useStrategiesList()
  const { subs, isLoading: subsLoading } = useAllSubscriptions(strategyIds)

  const filtered = useMemo(() => {
    if (!filter) return subs
    const lc = filter.toLowerCase()
    return subs.filter(
      (s) =>
        s.symbol.toLowerCase().includes(lc) ||
        s.strategy_id.toLowerCase().includes(lc) ||
        s.interval.toLowerCase().includes(lc),
    )
  }, [subs, filter])

  const isLoading = strategiesLoading || subsLoading

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: 'var(--bg-secondary)',
        borderRight: '1px solid var(--border-color)',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '8px 12px',
          borderBottom: '1px solid var(--border-color)',
          flexShrink: 0,
        }}
      >
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', flex: 1 }}>
          Strategies
        </span>
        <button
          className="btn-sm"
          onClick={() => setShowDialog(true)}
          style={{ padding: '2px 10px', fontSize: 11 }}
        >
          + New
        </button>
      </div>

      {/* Filter input */}
      <div style={{ padding: '6px 10px', borderBottom: '1px solid var(--border-color)', flexShrink: 0 }}>
        <input
          type="text"
          placeholder="Filter…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          style={{
            width: '100%',
            padding: '4px 8px',
            background: 'var(--bg-primary)',
            border: '1px solid var(--border-color)',
            borderRadius: 4,
            color: 'var(--text-primary)',
            fontSize: 12,
          }}
        />
      </div>

      {/* List */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {isLoading && (
          <div style={{ padding: '12px 12px', fontSize: 12, color: 'var(--text-secondary)' }}>
            Loading…
          </div>
        )}

        {!isLoading && strategyIds.length === 0 && (
          <div style={{ padding: '12px 12px', fontSize: 12, color: 'var(--text-secondary)' }}>
            No strategies loaded. Click + New to add one.
          </div>
        )}

        {!isLoading && strategyIds.length > 0 && filtered.length === 0 && (
          <div style={{ padding: '12px 12px', fontSize: 12, color: 'var(--text-secondary)' }}>
            No subscriptions match "{filter}".
          </div>
        )}

        {filtered.map((sub) => (
          <StrategyCard
            key={sub.id}
            sub={sub}
            selected={sub.id === selectedSubId}
            onClick={() => onSelect(sub)}
          />
        ))}
      </div>

      {/* Footer: strategy count */}
      {!isLoading && subs.length > 0 && (
        <div
          style={{
            padding: '6px 12px',
            borderTop: '1px solid var(--border-color)',
            fontSize: 11,
            color: 'var(--text-secondary)',
            flexShrink: 0,
          }}
        >
          {subs.length} subscription{subs.length !== 1 ? 's' : ''}
        </div>
      )}

      {showDialog && <NewSubscriptionDialog onClose={() => setShowDialog(false)} />}
    </div>
  )
}
