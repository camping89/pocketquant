interface StuckBadgeProps {
  show: boolean
}

export function StuckBadge({ show }: StuckBadgeProps) {
  if (!show) return null
  return (
    <span
      className="stuck-badge"
      role="status"
      aria-label="Sync is stuck — no new bars in 3× cadence"
      title="No new bars in 3× cadence"
    >
      stuck
    </span>
  )
}
