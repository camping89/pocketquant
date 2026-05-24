/**
 * Right pane of the strategies dashboard.
 * Composes: PnlBadge + EquitySparkline + MetricsTab + PositionsTab + RecentTradesTable.
 * Pulls data from backtest result for the selected subscription.
 */
import { useMemo, useState } from 'react'
import { useSubscriptionBacktest } from '../../hooks/use-subscriptions'
import { useOpenPosition } from '../../hooks/use-open-position'
import { useStrategyTrades } from '../../hooks/use-strategy-trades'
import { PnlBadge } from './pnl-badge'
import { EquitySparkline } from './equity-sparkline'
import { RecentTradesTable, type StrategyTrade } from './recent-trades-table'
import { MetricsTab } from '../strategy/backtest-panel/metrics-tab'
import { PositionsTab } from '../strategy/backtest-panel/positions-tab'
import type { Subscription } from '../../api/strategy-api'
import type { BacktestPosition } from '../../api/backtest-api'

type DashTab = 'metrics' | 'positions' | 'trades'

interface DashboardColumnProps {
  sub: Subscription
}

const TAB_LABELS: { key: DashTab; label: string }[] = [
  { key: 'metrics', label: 'Metrics' },
  { key: 'positions', label: 'Positions' },
  { key: 'trades', label: 'Trades' },
]

export function DashboardColumn({ sub }: DashboardColumnProps) {
  const [activeTab, setActiveTab] = useState<DashTab>('metrics')

  const { data: backtest, isLoading: btLoading } = useSubscriptionBacktest(
    sub.strategy_id,
    sub.id,
  )
  const { data: openPos } = useOpenPosition(sub.id)
  const { data: liveTrades = [] } = useStrategyTrades(sub.id)

  const equityCurve = backtest?.equity_curve ?? []
  const unrealizedPnl = openPos?.unrealized_pnl ?? 0

  // Prefer live closed positions; fall back to backtest positions for sandbox
  // subscriptions that have only been backtested.
  const trades = useMemo<StrategyTrade[]>(() => {
    if (liveTrades.length > 0) return liveTrades
    const positions = (backtest?.positions ?? []) as BacktestPosition[]
    return positions.map((p, idx) => ({
      id: `${idx}-${p.entry_time}`,
      direction: p.direction,
      entry_price: p.entry_price,
      exit_price: p.exit_price,
      entry_time: p.entry_time,
      exit_time: p.exit_time,
      pnl: p.pnl,
      quantity: p.quantity,
    }))
  }, [liveTrades, backtest?.positions])

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
      {/* Top summary strip */}
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
        <EquitySparkline equityCurve={equityCurve} />
      </div>

      {/* Tab bar */}
      <div
        style={{
          display: 'flex',
          gap: 2,
          padding: '4px 8px',
          borderBottom: '1px solid var(--border-color)',
          flexShrink: 0,
          background: 'var(--bg-primary)',
        }}
      >
        {TAB_LABELS.map(({ key, label }) => (
          <button
            key={key}
            className={`backtest-panel__tab${activeTab === key ? ' backtest-panel__tab--active' : ''}`}
            onClick={() => setActiveTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        {btLoading && (
          <div style={{ padding: 16, color: 'var(--text-secondary)', fontSize: 12 }}>
            Loading backtest…
          </div>
        )}

        {!btLoading && !backtest && (
          <div className="empty-state" style={{ padding: 24 }}>
            No backtest data. Run a backtest first.
          </div>
        )}

        {!btLoading && backtest && activeTab === 'metrics' && (
          <MetricsTab backtest={backtest} />
        )}

        {!btLoading && backtest && activeTab === 'positions' && (
          <PositionsTab
            backtest={backtest}
            highlightedIndex={null}
          />
        )}

        {!btLoading && backtest && activeTab === 'trades' && (
          <div style={{ padding: '0 0 8px' }}>
            <RecentTradesTable trades={trades} />
          </div>
        )}
      </div>
    </div>
  )
}
