import { useMemo, useState, type CSSProperties } from 'react'
import type { BacktestRunRow } from '../../api/backtest-api'

type SortKey = 'started_at' | 'total_return' | 'sharpe_ratio' | 'win_rate' | 'max_drawdown' | 'total_trades'

const th: CSSProperties = {
  textAlign: 'right',
  padding: '6px 8px',
  color: 'var(--text-secondary)',
  fontWeight: 600,
  borderBottom: '1px solid var(--border-color)',
  cursor: 'pointer',
  whiteSpace: 'nowrap',
}
const td: CSSProperties = { padding: '6px 8px', borderBottom: '1px solid var(--border-color)', textAlign: 'right' }

function metricVal(row: BacktestRunRow, key: SortKey): number {
  if (key === 'started_at') return new Date(row.started_at).getTime()
  return row.metrics ? (row.metrics[key] ?? 0) : 0
}

interface Props {
  rows: BacktestRunRow[]
  selected: string[]
  onToggleSelect: (runId: string) => void
  onRowClick: (runId: string) => void
}

/** History run list: client-side sort, row → detail, checkbox (≤3) → compare. */
export function BacktestHistoryTable({ rows, selected, onToggleSelect, onRowClick }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('started_at')
  const [desc, setDesc] = useState(true)

  const sorted = useMemo(() => {
    const out = [...rows].sort((a, b) => metricVal(a, sortKey) - metricVal(b, sortKey))
    return desc ? out.reverse() : out
  }, [rows, sortKey, desc])

  function sortBy(key: SortKey) {
    if (key === sortKey) setDesc((d) => !d)
    else {
      setSortKey(key)
      setDesc(true)
    }
  }

  const arrow = (key: SortKey) => (key === sortKey ? (desc ? ' ↓' : ' ↑') : '')
  const pct = (n: number | undefined) => (n == null ? '—' : (n * 100).toFixed(1) + '%')

  if (rows.length === 0) {
    return <div className="empty-state" style={{ padding: 16 }}>No runs for this scope yet.</div>
  }

  return (
    <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse', color: 'var(--text-primary)' }}>
      <thead>
        <tr>
          <th style={{ ...th, textAlign: 'center', cursor: 'default' }}></th>
          <th style={{ ...th, textAlign: 'left' }} onClick={() => sortBy('started_at')}>Started{arrow('started_at')}</th>
          <th style={{ ...th, textAlign: 'left', cursor: 'default' }}>Strategy</th>
          <th style={{ ...th, textAlign: 'left', cursor: 'default' }}>Symbol</th>
          <th style={th} onClick={() => sortBy('total_return')}>Return{arrow('total_return')}</th>
          <th style={th} onClick={() => sortBy('sharpe_ratio')}>Sharpe{arrow('sharpe_ratio')}</th>
          <th style={th} onClick={() => sortBy('win_rate')}>Win%{arrow('win_rate')}</th>
          <th style={th} onClick={() => sortBy('max_drawdown')}>Max DD{arrow('max_drawdown')}</th>
          <th style={th} onClick={() => sortBy('total_trades')}>#{arrow('total_trades')}</th>
          <th style={{ ...th, textAlign: 'left', cursor: 'default' }}>Verdict</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((r) => {
          const checked = selected.includes(r.id)
          const disable = !checked && selected.length >= 3
          return (
            <tr key={r.id}>
              <td style={{ ...td, textAlign: 'center' }}>
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={disable}
                  onChange={() => onToggleSelect(r.id)}
                  aria-label={`Select run ${r.id}`}
                />
              </td>
              <td style={{ ...td, textAlign: 'left', cursor: 'pointer' }} onClick={() => onRowClick(r.id)}>
                {r.started_at.replace('T', ' ').slice(0, 16)}
              </td>
              <td style={{ ...td, textAlign: 'left' }}>{r.strategy_code}</td>
              <td style={{ ...td, textAlign: 'left' }}>{r.symbol} · {r.interval}</td>
              <td style={{ ...td, color: (r.metrics?.total_return ?? 0) >= 0 ? 'var(--up-color)' : 'var(--down-color)' }}>{pct(r.metrics?.total_return)}</td>
              <td style={td}>{r.metrics ? r.metrics.sharpe_ratio.toFixed(2) : '—'}</td>
              <td style={td}>{pct(r.metrics?.win_rate)}</td>
              <td style={{ ...td, color: 'var(--down-color)' }}>{pct(r.metrics?.max_drawdown)}</td>
              <td style={td}>{r.metrics?.total_trades ?? '—'}</td>
              <td style={{ ...td, textAlign: 'left', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-secondary)' }} title={r.verdict ?? ''}>
                {r.verdict ?? '—'}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
