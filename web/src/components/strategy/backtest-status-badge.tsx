import type { BacktestStatus } from '../../api/backtest-api'

interface BacktestStatusBadgeProps {
  status: BacktestStatus | string | null
  errorMsg?: string | null
}

const STATUS_STYLES: Record<string, { bg: string; color: string; label: string }> = {
  started:  { bg: 'rgba(56,189,248,0.15)', color: '#38bdf8', label: 'running' },
  finished: { bg: 'rgba(38,166,154,0.15)', color: '#26a69a', label: 'done' },
  failed:   { bg: 'rgba(239,83,80,0.15)',  color: '#ef5350', label: 'failed' },
  none:     { bg: 'rgba(139,139,154,0.12)', color: '#8b8b9a', label: 'none' },
}

export function BacktestStatusBadge({ status, errorMsg }: BacktestStatusBadgeProps) {
  const key = status && STATUS_STYLES[status] ? status : 'none'
  const s = STATUS_STYLES[key]
  const title = errorMsg ? `Error: ${errorMsg}` : undefined

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
        cursor: title ? 'help' : 'default',
      }}
    >
      {key === 'started' && (
        <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: s.color, animation: 'status-pulse 1.4s ease infinite' }} />
      )}
      {s.label}
    </span>
  )
}
