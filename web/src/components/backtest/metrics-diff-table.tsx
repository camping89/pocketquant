import { type CSSProperties } from 'react'
import type { BacktestMetrics, BacktestRunResult } from '../../api/backtest-api'

type Direction = 'higher' | 'lower' | 'neutral'

// Per-metric "good" direction for best-cell highlight (validation Q4).
// 'higher' = bigger is better; 'lower' = smaller is better (incl. less-negative
// max_drawdown/avg_loss, since -0.05 > -0.20); 'neutral' = no highlight.
const METRIC_ROWS: { key: keyof BacktestMetrics; label: string; dir: Direction; fmt: (n: number) => string }[] = [
  { key: 'total_return', label: 'Total Return', dir: 'higher', fmt: (n) => (n * 100).toFixed(2) + '%' },
  { key: 'cagr', label: 'CAGR', dir: 'higher', fmt: (n) => (n * 100).toFixed(2) + '%' },
  { key: 'sharpe_ratio', label: 'Sharpe', dir: 'higher', fmt: (n) => n.toFixed(2) },
  { key: 'sortino_ratio', label: 'Sortino', dir: 'higher', fmt: (n) => n.toFixed(2) },
  { key: 'win_rate', label: 'Win Rate', dir: 'higher', fmt: (n) => (n * 100).toFixed(1) + '%' },
  { key: 'profit_factor', label: 'Profit Factor', dir: 'higher', fmt: (n) => (isFinite(n) ? n.toFixed(2) : '∞') },
  { key: 'avg_win', label: 'Avg Win', dir: 'higher', fmt: (n) => n.toFixed(2) },
  { key: 'max_drawdown', label: 'Max Drawdown', dir: 'higher', fmt: (n) => (n * 100).toFixed(2) + '%' },
  { key: 'avg_loss', label: 'Avg Loss', dir: 'higher', fmt: (n) => n.toFixed(2) },
  { key: 'total_commission', label: 'Total Commission', dir: 'lower', fmt: (n) => '$' + n.toFixed(2) },
  { key: 'avg_trade_duration_seconds', label: 'Avg Duration (s)', dir: 'lower', fmt: (n) => n.toFixed(0) },
  { key: 'total_trades', label: 'Total Trades', dir: 'neutral', fmt: (n) => n.toFixed(0) },
  { key: 'winning_trades', label: 'Winning', dir: 'neutral', fmt: (n) => n.toFixed(0) },
  { key: 'losing_trades', label: 'Losing', dir: 'neutral', fmt: (n) => n.toFixed(0) },
]

const th: CSSProperties = { textAlign: 'right', padding: '6px 10px', color: 'var(--text-secondary)', fontWeight: 600, borderBottom: '1px solid var(--border-color)' }
const td: CSSProperties = { textAlign: 'right', padding: '6px 10px', borderBottom: '1px solid var(--border-color)' }
const bestCell: CSSProperties = { ...td, background: 'color-mix(in srgb, var(--up-color) 18%, transparent)', fontWeight: 600 }

/** Find which run indexes hold the best value for a row's direction. Ties share
 *  the highlight; neutral rows never highlight; null values are skipped. */
function bestIndexes(values: (number | null)[], dir: Direction): Set<number> {
  if (dir === 'neutral') return new Set()
  const valid = values.map((v, i) => ({ v, i })).filter((x): x is { v: number; i: number } => x.v != null && isFinite(x.v))
  if (valid.length === 0) return new Set()
  const best = valid.reduce((acc, x) => {
    if (dir === 'higher') return x.v > acc ? x.v : acc
    return x.v < acc ? x.v : acc
  }, valid[0].v)
  return new Set(valid.filter((x) => x.v === best).map((x) => x.i))
}

/** Side-by-side metric comparison (columns = runs); best cell per row highlighted. */
export function MetricsDiffTable({ runs }: { runs: BacktestRunResult[] }) {
  return (
    <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse', color: 'var(--text-primary)' }}>
      <thead>
        <tr>
          <th style={{ ...th, textAlign: 'left' }}>Metric</th>
          {runs.map((r, i) => (
            <th key={i} style={th}>{r.strategy_code ?? `Run ${i + 1}`}<br /><span style={{ fontWeight: 400, fontSize: 10 }}>{String(r.config_snapshot?.symbol ?? r.id ?? '')}</span></th>
          ))}
        </tr>
      </thead>
      <tbody>
        {METRIC_ROWS.map((row) => {
          const values = runs.map((r) => (r.metrics ? r.metrics[row.key] : null))
          const best = bestIndexes(values, row.dir)
          return (
            <tr key={row.key}>
              <td style={{ ...td, textAlign: 'left', color: 'var(--text-secondary)' }}>{row.label}</td>
              {values.map((v, i) => (
                <td key={i} style={best.has(i) ? bestCell : td}>
                  {v == null ? '—' : row.fmt(v)}
                </td>
              ))}
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
