import { useState, type CSSProperties } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useStrategyList, useBacktestRuns } from '../../hooks/use-backtest-run'
import { SymbolSelector } from '../controls/symbol-selector'
import { BacktestHistoryTable } from './backtest-history-table'

const INTERVALS = ['', '1m', '5m', '15m', '1h', '4h', '1d']

const labelStyle: CSSProperties = { fontSize: 11, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }
const inputStyle: CSSProperties = {
  background: 'var(--bg-primary)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-color)',
  borderRadius: 4,
  padding: '5px 8px',
  fontSize: 13,
}

/** History rail: pick a strategy (validation Q5 — empty until then), optionally
 *  narrow by composite symbol + interval, then browse / select runs to compare. */
export function RunHistoryRail() {
  const navigate = useNavigate()
  const { data: strategies = [] } = useStrategyList()

  const [strategy, setStrategy] = useState('')
  const [symbol, setSymbol] = useState('') // composite CODE:EXCHANGE when set
  const [interval, setInterval] = useState('')
  const [selected, setSelected] = useState<string[]>([])

  const scope = strategy
    ? { strategy, symbol: symbol || undefined, interval: interval || undefined }
    : null
  const { data: rows = [], isLoading } = useBacktestRuns(scope)

  function toggleSelect(runId: string) {
    setSelected((prev) =>
      prev.includes(runId) ? prev.filter((r) => r !== runId) : prev.length < 3 ? [...prev, runId] : prev,
    )
  }

  return (
    <section style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: 8, padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>History</span>
        {selected.length >= 2 && (
          <button
            type="button"
            className="btn-sm"
            onClick={() => void navigate({ to: '/backtest/compare', search: { runs: selected } })}
          >
            Compare {selected.length}
          </button>
        )}
      </div>

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div>
          <label style={labelStyle}>Strategy</label>
          <select style={inputStyle} value={strategy} onChange={(e) => { setStrategy(e.target.value); setSelected([]) }}>
            <option value="">Select strategy…</option>
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
      </div>

      {!strategy ? (
        <div className="empty-state" style={{ padding: 16 }}>Select a strategy to view its run history.</div>
      ) : isLoading ? (
        <div className="empty-state" style={{ padding: 16 }}>Loading runs…</div>
      ) : (
        <BacktestHistoryTable
          rows={rows}
          selected={selected}
          onToggleSelect={toggleSelect}
          onRowClick={(runId) => void navigate({ to: '/backtest/$runId', params: { runId } })}
        />
      )}
    </section>
  )
}
