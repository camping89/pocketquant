interface BacktestStatusBadgeProps {
  status: 'running' | 'completed' | 'failed' | null
  lastRunAt?: string | null
  errorMsg?: string | null
}

const STATUS_STYLES: Record<string, { bg: string; color: string; label: string }> = {
  running:   { bg: 'rgba(56,189,248,0.15)', color: '#38bdf8', label: 'running' },
  completed: { bg: 'rgba(38,166,154,0.15)', color: '#26a69a', label: 'done' },
  failed:    { bg: 'rgba(239,83,80,0.15)',  color: '#ef5350', label: 'failed' },
  none:      { bg: 'rgba(139,139,154,0.12)', color: '#8b8b9a', label: 'none' },
}

function formatTitle(lastRunAt?: string | null, errorMsg?: string | null): string {
  const parts: string[] = []
  if (lastRunAt) parts.push(`Last run: ${new Date(lastRunAt).toLocaleString()}`)
  if (errorMsg)  parts.push(`Error: ${errorMsg}`)
  return parts.join('\n')
}

export function BacktestStatusBadge({ status, lastRunAt, errorMsg }: BacktestStatusBadgeProps) {
  const key = status ?? 'none'
  const s = STATUS_STYLES[key]
  const title = formatTitle(lastRunAt, errorMsg)

  return (
    <span
      title={title || undefined}
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
      {key === 'running' && (
        <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: s.color, animation: 'pulse 1.4s ease infinite' }} />
      )}
      {s.label}
    </span>
  )
}
