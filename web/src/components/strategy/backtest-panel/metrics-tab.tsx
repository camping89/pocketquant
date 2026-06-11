import { useMemo } from 'react'
import type { SubscriptionBacktest } from '../../../api/backtest-api'
import { MetricCard } from './metric-card'
import { buildMetricCards } from './metric-cards'

interface MetricsTabProps {
  backtest: SubscriptionBacktest
}

export function MetricsTab({ backtest }: MetricsTabProps) {
  const cards = useMemo(
    () => (backtest.metrics ? buildMetricCards(backtest.metrics) : null),
    [backtest.metrics],
  )

  if (!cards) {
    return (
      <div className="backtest-panel__tab-content">
        <div className="empty-state">No metrics available — backtest may have failed or has no closed positions.</div>
      </div>
    )
  }

  return (
    <div className="backtest-panel__tab-content metrics-tab">
      <div className="metrics-grid">
        {cards.map((card) => (
          <MetricCard key={card.key} card={card} />
        ))}
      </div>
    </div>
  )
}
