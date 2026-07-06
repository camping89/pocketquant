import type { BacktestRunRow } from '../../api/backtest-api'

interface RunListItemProps {
  row: BacktestRunRow
  active: boolean
  selected: boolean
  disableSelect: boolean
  onSelect: (runId: string) => void
  onToggleSelect: (runId: string) => void
}

const pct = (n: number | undefined | null) => (n == null ? '—' : (n * 100).toFixed(1) + '%')

/** Compact run row for the narrow master list. Two lines of essentials; a
 *  left accent border marks the active run; checkbox feeds the compare picker. */
export function RunListItem({ row, active, selected, disableSelect, onSelect, onToggleSelect }: RunListItemProps) {
  const ret = row.metrics?.total_return ?? 0
  return (
    <div
      className={`backtest-run-item${active ? ' backtest-run-item--active' : ''}`}
      onClick={() => onSelect(row.id)}
      role="button"
      tabIndex={0}
    >
      <div className="backtest-run-item__line1">
        <input
          type="checkbox"
          checked={selected}
          disabled={disableSelect}
          onClick={(e) => e.stopPropagation()}
          onChange={() => onToggleSelect(row.id)}
          aria-label={`Select run ${row.id}`}
        />
        <span style={{ fontWeight: 600 }}>{row.name || row.strategy_code}</span>
        {row.name && <span style={{ color: 'var(--text-secondary)' }}>{row.strategy_code}</span>}
        <span style={{ color: 'var(--text-secondary)' }}>{row.symbol} · {row.interval}</span>
      </div>
      <div className="backtest-run-item__line2">
        <span>{row.started_at.replace('T', ' ').slice(0, 16)}</span>
        <span style={{ color: ret >= 0 ? 'var(--up-color)' : 'var(--down-color)' }}>{pct(row.metrics?.total_return)}</span>
        <span>SR {row.metrics ? row.metrics.sharpe_ratio.toFixed(2) : '—'}</span>
        <span>{row.metrics?.total_trades ?? '—'} trades</span>
        {row.verdict && (
          <span className="backtest-run-item__verdict" title={row.verdict}>· {row.verdict}</span>
        )}
      </div>
    </div>
  )
}
