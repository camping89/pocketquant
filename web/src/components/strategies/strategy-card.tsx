/**
 * Single row in the strategy list sidebar.
 * Line 1: symbol code + exchange badge + PAPER/LIVE badge.
 * Line 2: timeframe · strategy code + one run-state pill.
 */
import { parseSymbol } from '../../lib/symbol-format'
import type { Subscription } from '../../api/strategy-api'

interface StrategyCardProps {
  sub: Subscription
  selected: boolean
  onClick: () => void
}

type RowState = 'running' | 'starting' | 'stopped'

/** Map forward run-state → the row's state pill. */
function toRowState(sub: Subscription): RowState {
  if (sub.actual_state === 'running') return 'running'
  if (sub.desired_state === 'running') return 'starting'  // converging
  return 'stopped'
}

export function StrategyCard({ sub, selected, onClick }: StrategyCardProps) {
  const { code, exchange } = parseSymbol(sub.symbol)
  const state = toRowState(sub)
  const live = sub.broker === 'exness'

  return (
    <button type="button"
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
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
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
          <span className={`mode ${live ? 'mode-live' : 'mode-paper'}`} title={`broker: ${sub.broker}`}>
            {live ? 'LIVE' : 'PAPER'}
          </span>
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            flexWrap: 'wrap',
            fontSize: 11,
            color: 'var(--text-secondary)',
            marginTop: 1,
          }}
        >
          {sub.interval} · {sub.strategy_code}
          <span className={`state-pill state-pill--${state}`}>{state.toUpperCase()}</span>
        </div>
      </div>
    </button>
  )
}
