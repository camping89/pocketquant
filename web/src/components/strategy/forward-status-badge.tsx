/**
 * Live/forward-execution status badge for a subscription.
 *
 * Derived from the control-plane pair (desired_state, actual_state):
 *   - actual=running                      → live (strategy trading on live feed)
 *   - desired=running & actual=stopped    → starting (reconcile converging)
 *   - desired=stopped & actual=running     → stopping (reconcile converging)
 *   - both stopped                        → stopped
 *
 * Sibling of BacktestStatusBadge so a SubRow shows backtest and forward state side by side.
 */
import type { RunState } from '../../api/strategy-api'

type ForwardKey = 'live' | 'starting' | 'stopping' | 'stopped'

function deriveForwardKey(desired: RunState, actual: RunState): ForwardKey {
  if (actual === 'running') return desired === 'running' ? 'live' : 'stopping'
  return desired === 'running' ? 'starting' : 'stopped'
}

const STATUS_STYLES: Record<ForwardKey, { bg: string; color: string; label: string; pulse: boolean }> = {
  live:     { bg: 'rgba(38,166,154,0.15)', color: '#26a69a', label: 'live',     pulse: true },
  starting: { bg: 'rgba(255,167,38,0.15)', color: '#ffa726', label: 'starting', pulse: true },
  stopping: { bg: 'rgba(255,167,38,0.15)', color: '#ffa726', label: 'stopping', pulse: true },
  stopped:  { bg: 'rgba(139,139,154,0.12)', color: '#8b8b9a', label: 'stopped',  pulse: false },
}

interface ForwardStatusBadgeProps {
  desiredState: RunState
  actualState: RunState
}

export function ForwardStatusBadge({ desiredState, actualState }: ForwardStatusBadgeProps) {
  const key = deriveForwardKey(desiredState, actualState)
  const s = STATUS_STYLES[key]
  const title =
    key === 'starting' || key === 'stopping'
      ? `Forward: ${s.label} (reconcile converging)`
      : `Forward: ${s.label}`

  return (
    <span
      title={title}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '2px 7px',
        borderRadius: 10,
        fontSize: 10,
        fontWeight: 600,
        letterSpacing: '0.04em',
        textTransform: 'uppercase',
        background: s.bg,
        color: s.color,
        whiteSpace: 'nowrap',
        cursor: 'help',
      }}
    >
      {s.pulse && (
        <span
          style={{
            display: 'inline-block',
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: s.color,
            animation: 'status-pulse 1.4s ease infinite',
          }}
        />
      )}
      {s.label}
    </span>
  )
}
