/** Large PnL display with +/- prefix and semantic color. */

interface PnlBadgeProps {
  pnl: number
  label?: string
}

export function PnlBadge({ pnl, label = 'Unrealized PnL' }: PnlBadgeProps) {
  const isPositive = pnl >= 0
  const color = isPositive ? 'var(--up-color)' : 'var(--down-color)'
  const prefix = isPositive ? '+' : ''

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-secondary)' }}>
        {label}
      </span>
      <span
        style={{
          fontSize: 24,
          fontWeight: 700,
          color,
          fontVariantNumeric: 'tabular-nums',
          letterSpacing: '-0.02em',
        }}
      >
        {prefix}{pnl.toFixed(2)}
      </span>
    </div>
  )
}
