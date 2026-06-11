interface StatusPillProps {
  variant: 'ok' | 'warn' | 'error' | 'neutral'
  label: string
  title?: string
}

export function StatusPill({ variant, label, title }: StatusPillProps) {
  return (
    <span className={`status-pill status-pill--${variant}`} title={title}>
      {label}
    </span>
  )
}
