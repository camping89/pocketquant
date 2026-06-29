/**
 * Right pane of the strategies dashboard — forward-testing only.
 * Composes: PnlBadge (unrealized) + live closed-trades table for the selected
 * subscription. Backtest now lives on its own /backtest page, decoupled from
 * subscriptions.
 */
import { useOpenPosition } from '../../hooks/use-open-position'
import { useStrategyTrades } from '../../hooks/use-strategy-trades'
import { PnlBadge } from './pnl-badge'
import { RecentTradesTable } from './recent-trades-table'
import type { Subscription } from '../../api/strategy-api'

interface DashboardColumnProps {
  sub: Subscription
}

export function DashboardColumn({ sub }: DashboardColumnProps) {
  const { data: openPos } = useOpenPosition(sub.id)
  const { data: liveTrades = [] } = useStrategyTrades(sub.id)

  const unrealizedPnl = openPos?.unrealized_pnl ?? 0

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: 'var(--bg-secondary)',
        borderLeft: '1px solid var(--border-color)',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          padding: '14px 16px 10px',
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
          flexShrink: 0,
        }}
      >
        <PnlBadge pnl={unrealizedPnl} label="Unrealized PnL" />
      </div>

      <div style={{ flex: 1, overflow: 'auto', minHeight: 0, padding: '0 0 8px' }}>
        {liveTrades.length === 0 ? (
          <div className="empty-state" style={{ padding: 24 }}>
            No closed trades yet.
          </div>
        ) : (
          <RecentTradesTable trades={liveTrades} />
        )}
      </div>
    </div>
  )
}
