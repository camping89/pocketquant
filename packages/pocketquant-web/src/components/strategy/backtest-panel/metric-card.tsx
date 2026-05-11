import type { MetricCardModel } from './metric-cards'

interface MetricCardProps {
  card: MetricCardModel
}

export function MetricCard({ card }: MetricCardProps) {
  return (
    <div className={`metric-card metric-card--${card.tone}`} title={card.tooltip}>
      <div className="metric-card__label">{card.label}</div>
      <div className="metric-card__value">{card.value}</div>
    </div>
  )
}
