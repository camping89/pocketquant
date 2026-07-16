/**
 * Left pane of the strategies dashboard.
 * Lists all subscriptions across all loaded strategies with filter + New button.
 */
import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { StrategyCard } from './strategy-card'
import { NewSubscriptionDialog } from './new-subscription-dialog'
import { listSubscriptions } from '../../api/strategy-api'
import type { Subscription } from '../../api/strategy-api'

interface StrategyListSidebarProps {
  selectedSubId: string | null
  onSelect: (sub: Subscription) => void
}

export function StrategyListSidebar({ selectedSubId, onSelect }: StrategyListSidebarProps) {
  const [showDialog, setShowDialog] = useState(false)
  const [filter, setFilter] = useState('')

  const { data: subs = [], isLoading } = useQuery({
    queryKey: ['subscriptions'],
    queryFn: () => listSubscriptions(),
    staleTime: 10_000,
    refetchInterval: 5_000,
  })

  const filtered = useMemo(() => {
    if (!filter) return subs
    const lc = filter.toLowerCase()
    return subs.filter(
      (s) =>
        s.symbol.toLowerCase().includes(lc) ||
        s.strategy_code.toLowerCase().includes(lc) ||
        s.interval.toLowerCase().includes(lc),
    )
  }, [subs, filter])

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
        <button type="button"
          className="btn-sm"
          onClick={() => setShowDialog(true)}
          style={{ padding: '2px 10px', fontSize: 11 }}
        >
          + New
        </button>
      </div>

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

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {isLoading && (
          <div style={{ padding: '12px 12px', fontSize: 12, color: 'var(--text-secondary)' }}>
            Loading…
          </div>
        )}

        {!isLoading && subs.length === 0 && (
          <div style={{ padding: '12px 12px', fontSize: 12, color: 'var(--text-secondary)' }}>
            No subscriptions yet. Click + New to add one.
          </div>
        )}

        {!isLoading && subs.length > 0 && filtered.length === 0 && (
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
