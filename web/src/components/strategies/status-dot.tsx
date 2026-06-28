/** Animated 12px status indicator dot for strategy running state. */

export type StrategyStatus = 'running' | 'idle' | 'stopped' | 'error' | 'starting' | 'stopping'

interface StatusDotProps {
  status: StrategyStatus
}

const DOT_COLORS: Record<StrategyStatus, string> = {
  running: '#26a69a',
  idle: '#607d8b',
  stopped: '#607d8b',
  error: '#ef5350',
  starting: '#ffa726',
  stopping: '#ffa726',
}

export function StatusDot({ status }: StatusDotProps) {
  const color = DOT_COLORS[status]
  const isPulsing = status === 'starting' || status === 'stopping'

  return (
    <span
      title={status}
      style={{
        display: 'inline-block',
        width: 12,
        height: 12,
        borderRadius: '50%',
        background: color,
        flexShrink: 0,
        animation: isPulsing ? 'status-pulse 1.2s ease-in-out infinite' : undefined,
      }}
    />
  )
}
