/** Chip displaying leverage tier with color coding. */

interface LeverageBadgeProps {
  leverage: number
}

function getTierColor(leverage: number): { bg: string; color: string } {
  if (leverage <= 5) return { bg: 'rgba(96,125,139,0.18)', color: '#90a4ae' }
  if (leverage <= 20) return { bg: 'rgba(255,167,38,0.15)', color: '#ffa726' }
  return { bg: 'rgba(239,83,80,0.15)', color: '#ef5350' }
}

export function LeverageBadge({ leverage }: LeverageBadgeProps) {
  const { bg, color } = getTierColor(leverage)
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: 4,
        fontSize: 11,
        fontWeight: 700,
        background: bg,
        color,
        fontVariantNumeric: 'tabular-nums',
      }}
    >
      {leverage}x
    </span>
  )
}
