import { useMemo, useState, type CSSProperties } from 'react'
import type { BacktestRunResult } from '../../api/backtest-api'
import { MetricCard } from '../strategy/backtest-panel/metric-card'
import { buildMetricCards, buildMetricGroups } from '../strategy/backtest-panel/metric-cards'
import { PositionsTab } from '../strategy/backtest-panel/positions-tab'
import { EquityDrawdownChart } from './equity-drawdown-chart'
import { PnlHistogram } from './pnl-histogram'
import { DurationHistogram } from './duration-histogram'
import { DrawdownTable } from './drawdown-table'
import { computeStreaks, profitFactorByDirection } from './stats-utils'
import { OrdersTable } from './orders-table'
import { VerdictPanel } from './verdict-panel'

type ResultTab = 'overview' | 'trades' | 'risk' | 'orders'

const TABS: { key: ResultTab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'trades', label: 'Trades' },
  { key: 'risk', label: 'Risk & Time' },
  { key: 'orders', label: 'Orders' },
]

const KPI_KEYS = ['total_return', 'cagr', 'sharpe', 'max_dd', 'win_rate']

const sectionTitle: CSSProperties = {
  fontSize: 12,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: 0.4,
  margin: '12px 0 6px',
}

export function BacktestResultView({ run, runId }: { run: BacktestRunResult; runId: string }) {
  const [tab, setTab] = useState<ResultTab>('overview')
  const metrics = run.metrics

  const kpiCards = useMemo(
    () => (metrics ? buildMetricCards(metrics).filter((c) => KPI_KEYS.includes(c.key)) : []),
    [metrics],
  )
  const groups = useMemo(() => (metrics ? buildMetricGroups(metrics) : []), [metrics])
  const streaks = useMemo(() => computeStreaks(run.positions), [run.positions])
  const pfSplit = useMemo(() => profitFactorByDirection(run.positions), [run.positions])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <VerdictPanel runId={runId} verdict={run.verdict} />

      <div style={{ display: 'flex', gap: 2, padding: '4px 0', borderBottom: '1px solid var(--border-color)' }}>
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            className={`backtest-panel__tab${tab === key ? ' backtest-panel__tab--active' : ''}`}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {kpiCards.length > 0 && (
            <div className="metrics-tab">
              <div className="metrics-grid">
                {kpiCards.map((c) => (
                  <MetricCard key={c.key} card={c} />
                ))}
              </div>
            </div>
          )}
          {groups.map((g) => (
            <div key={g.title}>
              <div style={sectionTitle}>{g.title}</div>
              <div className="metrics-tab">
                <div className="metrics-grid">
                  {g.cards.map((c) => (
                    <MetricCard key={c.key} card={c} />
                  ))}
                </div>
              </div>
            </div>
          ))}
          <div style={sectionTitle}>Equity & Drawdown</div>
          <EquityDrawdownChart equityCurve={run.equity_curve} />
        </div>
      )}

      {tab === 'trades' && (
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 12, padding: '8px 0' }}>
            <span>Max win streak: <strong style={{ color: 'var(--up-color)' }}>{streaks.maxWinStreak}</strong></span>
            <span>Max loss streak: <strong style={{ color: 'var(--down-color)' }}>{streaks.maxLossStreak}</strong></span>
            <span>PF (Long): <strong>{pfSplit.long == null ? '∞' : pfSplit.long.toFixed(2)}</strong></span>
            <span>PF (Short): <strong>{pfSplit.short == null ? '∞' : pfSplit.short.toFixed(2)}</strong></span>
            {metrics && <span>PF (All): <strong>{isFinite(metrics.profit_factor) ? metrics.profit_factor.toFixed(2) : '∞'}</strong></span>}
          </div>
          <div style={sectionTitle}>PnL distribution</div>
          <PnlHistogram positions={run.positions} />
          <div style={sectionTitle}>Duration distribution (hours)</div>
          <DurationHistogram positions={run.positions} />
          <div style={sectionTitle}>Trades</div>
          <PositionsTab backtest={run} highlightedIndex={null} />
        </div>
      )}

      {tab === 'risk' && (
        <div style={{ padding: '8px 0' }}>
          <div style={sectionTitle}>Worst drawdowns</div>
          <DrawdownTable equityCurve={run.equity_curve} />
        </div>
      )}

      {tab === 'orders' && <OrdersTable runId={runId} active={tab === 'orders'} />}
    </div>
  )
}
