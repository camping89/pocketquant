import type { IChartApi } from 'lightweight-charts'
import type { SubscriptionBacktest } from '../../../api/backtest-api'
import { useEquityPane } from './use-equity-pane'

interface EquityTabProps {
  backtest: SubscriptionBacktest
  chart: IChartApi | null
}

export function EquityTab({ backtest, chart }: EquityTabProps) {
  const equityCurve = backtest.equity_curve ?? []
  useEquityPane(chart, equityCurve)

  if (equityCurve.length === 0) {
    return (
      <div className="backtest-panel__tab-content">
        <div className="empty-state">No equity data available.</div>
      </div>
    )
  }

  return (
    <div className="backtest-panel__tab-content">
      <div className="equity-tab__hint">
        Equity curve and drawdown rendered as a sub-pane on the main chart. {equityCurve.length} points.
      </div>
    </div>
  )
}
