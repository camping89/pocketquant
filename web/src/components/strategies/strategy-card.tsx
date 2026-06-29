/**
 * Single row in the strategy list sidebar.
 * Shows status dot + symbol code + exchange badge + timeframe.
 */
import { StatusDot, type StrategyStatus } from './status-dot'
import { parseSymbol } from '../../lib/symbol-format'
import type { Subscription } from '../../api/strategy-api'

interface StrategyCardProps {
  sub: Subscription
  selected: boolean
  onClick: () => void
}

/** Map forward run-state → strategy display status. */
function toStrategyStatus(sub: Subscription): StrategyStatus {
  if (sub.actual_state === 'running') return 'running'
  if (sub.desired_state === 'running') return 'starting'  // converging
  return 'idle'
}

export function StrategyCard({ sub, selected, onClick }: StrategyCardProps) {
  const { code, exchange } = parseSymbol(sub.symbol)
  const status = toStrategyStatus(sub)

  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        width: '100%',
        padding: '8px 12px',
        background: selected ? 'rgba(38,166,154,0.10)' : 'transparent',
        borderLeft: `3px solid ${selected ? 'var(--accent)' : 'transparent'}`,
        border: 'none',
        borderBottom: '1px solid var(--border-color)',
        cursor: 'pointer',
        textAlign: 'left',
        transition: 'background 0.12s',
      }}
    >
      <StatusDot status={status} />

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
            {code}
          </span>
          {exchange && (
            <span
              style={{
                fontSize: 10,
                fontWeight: 600,
                padding: '1px 5px',
                borderRadius: 3,
                background: 'rgba(96,125,139,0.2)',
                color: '#90a4ae',
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
              }}
            >
              {exchange}
            </span>
          )}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 1 }}>
          {sub.interval} · {sub.strategy_code}
        </div>
      </div>
    </button>
  )
}
