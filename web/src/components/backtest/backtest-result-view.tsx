import { useMemo, useState, type CSSProperties } from 'react'
import type { BacktestRunResult, TradeRow } from '../../api/backtest-api'
import type { IndicatorConfig, Interval } from '../../types/market-data'
import { useBacktestMarkers, useBacktestStats } from '../../hooks/use-backtest-run'
import { MetricCard } from '../strategy/backtest-panel/metric-card'
import { buildMetricCards, buildMetricGroups } from '../strategy/backtest-panel/metric-cards'
import { PositionsTab } from '../strategy/backtest-panel/positions-tab'
import { OpenPositionsTab } from '../strategy/backtest-panel/open-positions-tab'
import { TradingChart } from '../chart/trading-chart'
import { EquityDrawdownChart } from './equity-drawdown-chart'
import { PnlHistogram } from './pnl-histogram'
import { DurationHistogram } from './duration-histogram'
import { DrawdownTable } from './drawdown-table'
import { OrdersTable } from './orders-table'
import { VerdictPanel } from './verdict-panel'

type ResultTab = 'overview' | 'trades' | 'open' | 'risk' | 'orders'

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
  { key: 'open', label: 'Open Positions' },
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
  // Selection is by trade object (stable trade_id), so it survives paging +
  // server-side re-sorts. The clicked/hovered TradeRow feeds the chart's box.
  const [highlightedTrade, setHighlightedTrade] = useState<TradeRow | null>(null)
  const [hoveredTrade, setHoveredTrade] = useState<TradeRow | null>(null)
  const metrics = run.metrics
  const isFinished = run.status === 'finished'
  const tradesActive = tab === 'trades' && isFinished
  // Stats feed the Overview tab (histograms), the Trades tab (streaks, PF) AND
  // the Risk tab (drawdown periods), so fetch for any of them.
  const statsActive = (tab === 'overview' || tab === 'trades' || tab === 'risk') && isFinished

  const markersQuery = useBacktestMarkers(runId, tradesActive)
  const statsQuery = useBacktestStats(runId, statsActive)

  // Drop chart/table selection when switching to another run — a stale trade
  // would highlight against the new run's data. Adjust during render (not an
  // effect) so selection clears before the chart paints.
  const [prevRunId, setPrevRunId] = useState(runId)
  if (runId !== prevRunId) {
    setPrevRunId(runId)
    setHighlightedTrade(null)
    setHoveredTrade(null)
  }

  const kpiCards = useMemo(
    () => (metrics ? buildMetricCards(metrics).filter((c) => KPI_KEYS.includes(c.key)) : []),
    [metrics],
  )
  const groups = useMemo(() => (metrics ? buildMetricGroups(metrics) : []), [metrics])
  const stats = statsQuery.data
  const pfLong = stats?.profit_factor_by_direction.long
  const pfShort = stats?.profit_factor_by_direction.short

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
          <div style={sectionTitle}>PnL distribution</div>
          <PnlHistogram bins={stats?.pnl_histogram ?? []} />
          <div style={sectionTitle}>Duration distribution (hours)</div>
          <DurationHistogram bins={stats?.duration_histogram ?? []} />
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
                markers={markersQuery.data}
                highlightedTrade={highlightedTrade}
                hoveredTrade={hoveredTrade}
                onSelectTrade={setHighlightedTrade}
                anchorEndDate={run.end_date}
              />
            </div>
          ) : (
            <div className="empty-state">Symbol/interval không khả dụng cho run này.</div>
          )}
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 12, padding: '8px 0' }}>
            <span>Max win streak: <strong style={{ color: 'var(--up-color)' }}>{stats?.streaks.max_win_streak ?? '—'}</strong></span>
            <span>Max loss streak: <strong style={{ color: 'var(--down-color)' }}>{stats?.streaks.max_loss_streak ?? '—'}</strong></span>
            <span>PF (Long): <strong>{pfLong == null ? '∞' : pfLong.toFixed(2)}</strong></span>
            <span>PF (Short): <strong>{pfShort == null ? '∞' : pfShort.toFixed(2)}</strong></span>
            {stats && <span>PF (All): <strong>{isFinite(stats.profit_factor_all) ? stats.profit_factor_all.toFixed(2) : '∞'}</strong></span>}
          </div>
          <div style={sectionTitle}>Trades</div>
          <PositionsTab
            runId={runId}
            enabled={isFinished}
            highlightedTradeId={highlightedTrade?.trade_id ?? null}
            onTradeClick={setHighlightedTrade}
            onTradeHover={setHoveredTrade}
          />
        </div>
      )}

      {tab === 'open' && <OpenPositionsTab positions={run.open_positions} />}

      {tab === 'risk' && (
        <div style={{ padding: '8px 0' }}>
          <div style={sectionTitle}>Worst drawdowns</div>
          <DrawdownTable periods={stats?.drawdowns ?? []} />
        </div>
      )}

      {tab === 'orders' && <OrdersTable runId={runId} active={tab === 'orders'} />}
    </div>
  )
}
