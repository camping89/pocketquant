import { useState, type FormEvent } from 'react'
import { useStrategyList } from '../../hooks/use-backtest-run'
import type { RunBacktestBody } from '../../api/backtest-api'

const INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d']

interface BacktestFormProps {
  onSubmit: (body: RunBacktestBody) => void
  submitting: boolean
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 11,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  marginBottom: 4,
}
const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '6px 10px',
  background: 'var(--bg-primary)',
  border: '1px solid var(--border-color)',
  borderRadius: 4,
  color: 'var(--text-primary)',
  fontSize: 13,
}

export function BacktestForm({ onSubmit, submitting }: BacktestFormProps) {
  const { data: strategies = [], isLoading: stratLoading } = useStrategyList()
  const [strategyId, setStrategyId] = useState('')
  const [symbol, setSymbol] = useState('BTCUSDT:BINANCE')
  const [interval, setInterval] = useState('1m')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [paramsText, setParamsText] = useState('')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // Default the strategy dropdown to the first available once loaded.
  const effectiveStrategy = strategyId || strategies[0] || ''

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setErrorMsg(null)

    const sym = symbol.trim().toUpperCase()
    if (!effectiveStrategy) { setErrorMsg('Select a strategy.'); return }
    if (!sym.includes(':')) { setErrorMsg('Symbol must be CODE:EXCHANGE (e.g. BTCUSDT:BINANCE).'); return }
    if (!startDate || !endDate) { setErrorMsg('Start and end dates are required.'); return }
    if (startDate > endDate) { setErrorMsg('Start date must be on or before end date.'); return }

    let parameters: Record<string, unknown> | undefined
    if (paramsText.trim()) {
      try {
        parameters = JSON.parse(paramsText)
      } catch {
        setErrorMsg('Parameters must be valid JSON (e.g. {"direction": "long"}).')
        return
      }
    }

    onSubmit({
      strategy_id: effectiveStrategy,
      symbol: sym,
      interval,
      start_date: startDate,
      end_date: endDate,
      parameters,
    })
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div>
        <label style={labelStyle}>Strategy</label>
        <select
          style={inputStyle}
          value={effectiveStrategy}
          onChange={(e) => setStrategyId(e.target.value)}
          disabled={stratLoading}
        >
          {strategies.length === 0 && <option value="">{stratLoading ? 'Loading…' : 'None'}</option>}
          {strategies.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      <div>
        <label style={labelStyle}>Symbol</label>
        <input
          style={inputStyle}
          type="text"
          placeholder="BTCUSDT:BINANCE"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          onBlur={(e) => setSymbol(e.target.value.trim().toUpperCase())}
        />
      </div>

      <div style={{ display: 'flex', gap: 12 }}>
        <div style={{ flex: 1 }}>
          <label style={labelStyle}>Interval</label>
          <select style={inputStyle} value={interval} onChange={(e) => setInterval(e.target.value)}>
            {INTERVALS.map((iv) => <option key={iv} value={iv}>{iv}</option>)}
          </select>
        </div>
        <div style={{ flex: 1 }}>
          <label style={labelStyle}>Start date</label>
          <input style={inputStyle} type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
        </div>
        <div style={{ flex: 1 }}>
          <label style={labelStyle}>End date</label>
          <input style={inputStyle} type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
        </div>
      </div>

      <div>
        <label style={labelStyle}>Parameters (JSON, optional)</label>
        <textarea
          style={{ ...inputStyle, fontFamily: 'monospace', minHeight: 60, resize: 'vertical' }}
          placeholder='{"direction": "long", "key_level_lookback_bars": 5}'
          value={paramsText}
          onChange={(e) => setParamsText(e.target.value)}
        />
      </div>

      {errorMsg && (
        <div style={{ padding: '6px 10px', background: 'rgba(239,83,80,.1)', border: '1px solid rgba(239,83,80,.3)', borderRadius: 4, color: '#ef5350', fontSize: 12 }}>
          {errorMsg}
        </div>
      )}

      <button type="submit" className="btn-sm" disabled={submitting} style={{ alignSelf: 'flex-start', padding: '6px 16px' }}>
        {submitting ? 'Starting…' : 'Run Backtest'}
      </button>
    </form>
  )
}
