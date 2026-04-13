interface StatusPillProps {
  variant: 'ok' | 'warn' | 'error' | 'neutral'
  label: string
}

export function StatusPill({ variant, label }: StatusPillProps) {
  return <span className={`status-pill status-pill--${variant}`}>{label}</span>
}
