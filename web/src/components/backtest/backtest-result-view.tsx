import { useMemo, useState, type CSSProperties } from 'react'
import type { BacktestRunResult } from '../../api/backtest-api'
import type { IndicatorConfig, Interval } from '../../types/market-data'
import { MetricCard } from '../strategy/backtest-panel/metric-card'
import { buildMetricCards, buildMetricGroups } from '../strategy/backtest-panel/metric-cards'
import { PositionsTab } from '../strategy/backtest-panel/positions-tab'
import { TradingChart } from '../chart/trading-chart'
import { EquityDrawdownChart } from './equity-drawdown-chart'
import { PnlHistogram } from './pnl-histogram'
import { DurationHistogram } from './duration-histogram'
import { DrawdownTable } from './drawdown-table'
import { computeStreaks, profitFactorByDirection } from './stats-utils'
import { OrdersTable } from './orders-table'
import { VerdictPanel } from './verdict-panel'

type ResultTab = 'overview' | 'trades' | 'risk' | 'orders'

// Backtest chart shows raw price + trade markers/boxes only — live overlays
// (EMA, engulfing) belong to the realtime chart, not the post-mortem view.
const NO_INDICATORS: IndicatorConfig = {
  sma: false,
  ema: false,
  rsi: false,
  macd: false,
  bollinger: false,
  engulfing: false,
}

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
  const [highlightedIndex, setHighlightedIndex] = useState<number | null>(null)
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)
  const metrics = run.metrics

  // Drop chart/table selection when switching to another run — a stale index
  // would highlight the wrong trade against the new run's positions. Adjust
  // during render (not an effect) so selection clears before the chart paints.
  const [prevRunId, setPrevRunId] = useState(runId)
  if (runId !== prevRunId) {
    setPrevRunId(runId)
    setHighlightedIndex(null)
    setHoveredIndex(null)
  }

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
          {run.symbol && run.interval ? (
            <div className="backtest-trades-chart">
              <TradingChart
                symbol={run.symbol}
                interval={run.interval as Interval}
                indicators={NO_INDICATORS}
                positions={run.positions}
                highlightedPositionIndex={highlightedIndex}
                hoveredPositionIndex={hoveredIndex}
                anchorEndDate={run.end_date}
              />
            </div>
          ) : (
            <div className="empty-state">Symbol/interval không khả dụng cho run này.</div>
          )}
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
          <PositionsTab
            backtest={run}
            highlightedIndex={highlightedIndex}
            onPositionClick={(index) => setHighlightedIndex(index)}
            onPositionHover={(index) => setHoveredIndex(index)}
          />
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
