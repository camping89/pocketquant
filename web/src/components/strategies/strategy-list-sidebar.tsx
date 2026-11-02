import { useState, useMemo } from 'react'
import { StrategyCard } from './strategy-card'
import { SubscriptionFormDialog } from './subscription-form-dialog'
import { errorText } from '../../lib/subscription-view'
import type { Subscription } from '../../api/strategy-api'

interface StrategyListSidebarProps {
  subs: Subscription[]
  isLoading: boolean
  error: unknown
  selectedSubId: string | null
  onSelect: (sub: Subscription) => void
}

export function StrategyListSidebar({ subs, isLoading, error, selectedSubId, onSelect }: StrategyListSidebarProps) {
  const [showDialog, setShowDialog] = useState(false)
  // Only the id: the form reads the row from the polled list, so its stopped check stays current.
  const [editId, setEditId] = useState<string | null>(null)
  const editSub = subs.find((s) => s.id === editId)
  const [filter, setFilter] = useState('')

  const filtered = useMemo(() => {
    if (!filter) return subs
    const lc = filter.toLowerCase()
    return subs.filter(
      (s) =>
        s.symbol.toLowerCase().includes(lc) ||
        s.strategy_code.toLowerCase().includes(lc) ||
        s.intervals.join(' ').toLowerCase().includes(lc),
    )
  }, [subs, filter])

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: 'var(--bg-secondary)',
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
          title="New subscription"
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
        {error != null && <div className="drawer-error" style={{ margin: 8 }}>{errorText(error)}</div>}

        {isLoading && (
          <div style={{ padding: '12px 12px', fontSize: 12, color: 'var(--text-secondary)' }}>
            Loading…
          </div>
        )}

        {!isLoading && error == null && subs.length === 0 && (
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
            onOpen={() => onSelect(sub)}
            onEdit={() => setEditId(sub.id)}
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

      {showDialog && <SubscriptionFormDialog onClose={() => setShowDialog(false)} />}
      {editSub && <SubscriptionFormDialog sub={editSub} onClose={() => setEditId(null)} />}
    </div>
  )
}
