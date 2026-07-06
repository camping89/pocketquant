import type { BacktestMetrics } from '../../../api/backtest-api'

export type Tone = 'positive' | 'negative' | 'neutral'

export interface MetricCardModel {
  key: string
  label: string
  value: string
  tone: Tone
  tooltip: string
}

function fmtPct(n: number, signed = true): string {
  const v = (n * 100).toFixed(2) + '%'
  return signed && n > 0 ? `+${v}` : v
}

function fmtNumber(n: number, signed = false, decimals = 2): string {
  const s = n.toFixed(decimals)
  return signed && n > 0 ? `+${s}` : s
}

function fmtInt(n: number): string {
  return n.toFixed(0)
}

export function fmtDuration(seconds: number | null): string {
  if (seconds == null || !isFinite(seconds) || seconds <= 0) return '—'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${mins}m`
  if (mins > 0) return `${mins}m`
  return `${Math.round(seconds)}s`
}

function tonePnl(n: number): Tone {
  if (n > 0) return 'positive'
  if (n < 0) return 'negative'
  return 'neutral'
}

function toneSharpe(n: number): Tone {
  if (n >= 1) return 'positive'
  if (n < 0) return 'negative'
  return 'neutral'
}

function toneWinRate(n: number): Tone {
  if (n >= 0.5) return 'positive'
  if (n < 0.4) return 'negative'
  return 'neutral'
}

function toneProfitFactor(n: number): Tone {
  if (!isFinite(n) || n >= 1.5) return 'positive'
  if (n < 1) return 'negative'
  return 'neutral'
}

export interface MetricGroup {
  title: string
  cards: MetricCardModel[]
}

// Group → metric keys (validation Q1). Returns/Risk/Trade Stats; keys map to the
// `key` field of buildMetricCards so formatting/tone stays single-sourced.
const METRIC_GROUPS: { title: string; keys: string[] }[] = [
  { title: 'Returns', keys: ['total_return', 'cagr', 'avg_win', 'avg_loss'] },
  { title: 'Risk', keys: ['sharpe', 'sortino', 'max_dd', 'profit_factor'] },
  {
    title: 'Trade Stats',
    keys: ['total_trades', 'winning', 'losing', 'win_rate', 'avg_duration'],
  },
]

/** buildMetricCards partitioned into the 3 dashboard groups. total_commission is
 *  surfaced separately via buildCostCards (the Overview "Costs" section), so it
 *  is intentionally absent here. */
export function buildMetricGroups(m: BacktestMetrics): MetricGroup[] {
  const byKey = new Map(buildMetricCards(m).map((c) => [c.key, c]))
  return METRIC_GROUPS.map((g) => ({
    title: g.title,
    cards: g.keys.map((k) => byKey.get(k)).filter((c): c is MetricCardModel => c != null),
  }))
}

/** Coerce a config_snapshot value (typed `unknown`) to a finite number, else null. */
function num(v: unknown): number | null {
  return typeof v === 'number' && isFinite(v) ? v : null
}

/** A per-fill rate in bps rendered with its percent equivalent (1 bp = 0.01%).
 *  Old runs may lack the field → em dash. */
function fmtBpsRate(bps: number | null): string {
  if (bps == null) return '—'
  return `${bps} bps (${(bps / 100).toFixed(2)}%)`
}

/** Every cost the user is charged, for the Overview "Costs" section: the per-fill
 *  commission + slippage RATES (from the run's config snapshot, so each run shows
 *  the exact settings it ran with) and the total commission actually paid (USD).
 *  Slippage has no USD line — it is baked into fill prices, so it already lives
 *  inside every trade's PnL. */
export function buildCostCards(
  cfg: Record<string, unknown>,
  m: BacktestMetrics,
): MetricCardModel[] {
  const feesCard = buildMetricCards(m).find((c) => c.key === 'total_commission')
  const cards: MetricCardModel[] = [
    {
      key: 'commission_bps',
      label: 'Commission',
      value: fmtBpsRate(num(cfg.commission_bps)),
      tone: 'neutral',
      tooltip: 'Rate charged on every fill — debited from cash balance',
    },
    {
      key: 'slippage_bps',
      label: 'Slippage',
      value: fmtBpsRate(num(cfg.slippage_bps)),
      tone: 'neutral',
      tooltip: 'Rate applied on every fill — baked into entry/exit prices, so already in PnL',
    },
  ]
  if (feesCard) cards.push(feesCard)
  return cards
}

export function buildMetricCards(m: BacktestMetrics): MetricCardModel[] {
  return [
    {
      key: 'total_return',
      label: 'Total Return',
      value: fmtPct(m.total_return),
      tone: tonePnl(m.total_return),
      tooltip: '(final equity − initial) / initial',
    },
    {
      key: 'cagr',
      label: 'CAGR',
      value: fmtPct(m.cagr),
      tone: tonePnl(m.cagr),
      tooltip: 'Compound annual growth rate',
    },
    {
      key: 'sharpe',
      label: 'Sharpe',
      value: fmtNumber(m.sharpe_ratio),
      tone: toneSharpe(m.sharpe_ratio),
      tooltip: 'Risk-adjusted return (higher = better)',
    },
    {
      key: 'sortino',
      label: 'Sortino',
      value: fmtNumber(m.sortino_ratio),
      tone: toneSharpe(m.sortino_ratio),
      tooltip: 'Downside risk-adjusted return',
    },
    {
      key: 'max_dd',
      label: 'Max Drawdown',
      value: fmtPct(m.max_drawdown, false),
      tone: 'negative',
      tooltip: 'Largest peak-to-trough decline',
    },
    {
      key: 'win_rate',
      label: 'Win Rate',
      value: (m.win_rate * 100).toFixed(1) + '%',
      tone: toneWinRate(m.win_rate),
      tooltip: 'Winning positions / total positions',
    },
    {
      key: 'profit_factor',
      label: 'Profit Factor',
      value: isFinite(m.profit_factor) ? m.profit_factor.toFixed(2) : '∞',
      tone: toneProfitFactor(m.profit_factor),
      tooltip: 'Gross profit / gross loss',
    },
    {
      key: 'total_trades',
      label: 'Total Trades',
      value: fmtInt(m.total_trades),
      tone: 'neutral',
      tooltip: 'Count of closed positions',
    },
    {
      key: 'winning',
      label: 'Winning',
      value: fmtInt(m.winning_trades),
      tone: 'positive',
      tooltip: 'Positions with PnL > 0',
    },
    {
      key: 'losing',
      label: 'Losing',
      value: fmtInt(m.losing_trades),
      tone: 'negative',
      tooltip: 'Positions with PnL < 0',
    },
    {
      key: 'avg_win',
      label: 'Avg Win',
      value: fmtNumber(m.avg_win, true),
      tone: 'positive',
      tooltip: 'Mean PnL of winning positions',
    },
    {
      key: 'avg_loss',
      label: 'Avg Loss',
      value: fmtNumber(m.avg_loss, true),
      tone: 'negative',
      tooltip: 'Mean PnL of losing positions',
    },
    {
      key: 'avg_duration',
      label: 'Avg Duration',
      value: fmtDuration(m.avg_trade_duration_seconds),
      tone: 'neutral',
      tooltip: 'Average time from entry to exit',
    },
    {
      key: 'total_commission',
      label: 'Total Commission',
      value: `$${m.total_commission.toFixed(2)}`,
      tone: 'neutral',
      tooltip: 'Sum of all commissions paid (USD)',
    },
  ]
}
