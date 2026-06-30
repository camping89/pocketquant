import { useMemo, useState, type CSSProperties } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useStrategyList, useBacktestRuns, useAllBacktestRuns, useRunBacktest } from '../../hooks/use-backtest-run'
import type { BacktestRunRow } from '../../api/backtest-api'
import { SymbolSelector } from '../controls/symbol-selector'
import { RunListItem } from './run-list-item'
import { BacktestForm } from './backtest-form'

const INTERVALS = ['', '1m', '5m', '15m', '1h', '4h', '1d']

type SortKey = 'started_at' | 'total_return' | 'sharpe_ratio' | 'win_rate' | 'max_drawdown' | 'total_trades'

const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: 'started_at', label: 'Newest' },
  { key: 'total_return', label: 'Return' },
  { key: 'sharpe_ratio', label: 'Sharpe' },
  { key: 'win_rate', label: 'Win%' },
  { key: 'max_drawdown', label: 'Max DD' },
  { key: 'total_trades', label: '#Trades' },
]

function metricVal(row: BacktestRunRow, key: SortKey): number {
  if (key === 'started_at') return new Date(row.started_at).getTime()
  return row.metrics ? (row.metrics[key] ?? 0) : 0
}

const labelStyle: CSSProperties = { fontSize: 11, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }
const inputStyle: CSSProperties = {
  background: 'var(--bg-primary)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-color)',
  borderRadius: 4,
  padding: '5px 8px',
  fontSize: 13,
}

interface RunHistoryRailProps {
  selectedRun: string | null
  onSelect: (runId: string) => void
}

/** History rail: defaults to "All" strategies; narrow by strategy / composite
 *  symbol / interval via the pickers, then browse, sort, or select runs to
 *  compare. "+ New run" opens the backtest form in a drawer. */
export function RunHistoryRail({ selectedRun, onSelect }: RunHistoryRailProps) {
  const navigate = useNavigate()
  const { data: strategies = [] } = useStrategyList()
  const runBacktest = useRunBacktest()

  const [strategy, setStrategy] = useState('') // '' = All
  const [symbol, setSymbol] = useState('') // composite CODE:EXCHANGE when set
  const [interval, setInterval] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [sortKey, setSortKey] = useState<SortKey>('started_at')
  const [formOpen, setFormOpen] = useState(false)

  const narrowing = { symbol: symbol || undefined, interval: interval || undefined }
  const allRuns = useAllBacktestRuns(narrowing, strategy === '')
  const scopedRuns = useBacktestRuns(strategy ? { strategy, ...narrowing } : null)
  const { data: rows = [], isLoading } = strategy === '' ? allRuns : scopedRuns

  // Newest first for time; for metrics, larger is "better" so default desc too.
  const sorted = useMemo(
    () => [...rows].sort((a, b) => metricVal(b, sortKey) - metricVal(a, sortKey)),
    [rows, sortKey],
  )

  function toggleSelect(runId: string) {
    setSelected((prev) =>
      prev.includes(runId) ? prev.filter((r) => r !== runId) : prev.length < 3 ? [...prev, runId] : prev,
    )
  }

  return (
    <section style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>History</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {selected.length >= 2 && (
            <button
              type="button"
              className="btn-sm"
              onClick={() => void navigate({ to: '/backtest/compare', search: { runs: selected } })}
            >
              Compare {selected.length}
            </button>
          )}
          <button type="button" className="btn-sm" onClick={() => setFormOpen(true)}>+ New run</button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div>
          <label style={labelStyle}>Strategy</label>
          <select style={inputStyle} value={strategy} onChange={(e) => { setStrategy(e.target.value); setSelected([]) }}>
            <option value="">All strategies</option>
            {strategies.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label style={labelStyle}>Symbol (optional)</label>
          <SymbolSelector value={symbol} onChange={setSymbol} />
        </div>
        <div>
          <label style={labelStyle}>Interval (optional)</label>
          <select style={inputStyle} value={interval} onChange={(e) => setInterval(e.target.value)}>
            {INTERVALS.map((iv) => <option key={iv} value={iv}>{iv || 'Any'}</option>)}
          </select>
        </div>
        <div>
          <label style={labelStyle}>Sort</label>
          <select style={inputStyle} value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)}>
            {SORT_OPTIONS.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
          </select>
        </div>
      </div>

      {isLoading ? (
        <div className="empty-state" style={{ padding: 16 }}>Loading runs…</div>
      ) : sorted.length === 0 ? (
        <div className="empty-state" style={{ padding: 16 }}>No runs for this scope yet.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {sorted.map((r) => {
            const checked = selected.includes(r.id)
            return (
              <RunListItem
                key={r.id}
                row={r}
                active={selectedRun === r.id}
                selected={checked}
                disableSelect={!checked && selected.length >= 3}
                onSelect={onSelect}
                onToggleSelect={toggleSelect}
              />
            )
          })}
        </div>
      )}

      {formOpen && (
        <>
          <div className="drawer-backdrop" onClick={() => setFormOpen(false)} aria-hidden />
          <aside className="drawer" role="dialog" aria-modal="true" aria-label="Run backtest">
            <header className="drawer-header">
              <span className="drawer-title">Run Backtest</span>
              <button className="drawer-close" onClick={() => setFormOpen(false)} aria-label="Close">×</button>
            </header>
            <BacktestForm
              submitting={runBacktest.isPending}
              onSubmit={(body) => runBacktest.mutate(body, { onSuccess: () => setFormOpen(false) })}
            />
            {runBacktest.isError && (
              <div className="drawer-error" style={{ marginTop: 12 }}>
                {(runBacktest.error as Error)?.message ?? 'Failed to start backtest.'}
              </div>
            )}
          </aside>
        </>
      )}
    </section>
  )
}
