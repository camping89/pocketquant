import { useState, type FormEvent } from 'react'
import { useAddSymbol } from '../../hooks/use-subscriptions'

const EXCHANGES = ['OKX', 'BINANCE']
const INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d']

interface AddSymbolDialogProps {
  strategyId: string
  onClose: () => void
}

export function AddSymbolDialog({ strategyId, onClose }: AddSymbolDialogProps) {
  const [symbol, setSymbol] = useState('')
  const [exchange, setExchange] = useState('OKX')
  const [interval, setInterval] = useState('1h')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const addSymbol = useAddSymbol(strategyId)

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setErrorMsg(null)
    const trimmed = symbol.trim().toUpperCase()
    if (!trimmed) { setErrorMsg('Symbol is required'); return }

    addSymbol.mutate(
      { symbol: trimmed, exchange, interval },
      {
        onSuccess: () => { onClose() },
        onError: (err: unknown) => {
          const status = (err as { status?: number })?.status
          if (status === 409) setErrorMsg('Subscription already exists for this symbol/interval.')
          else if (status === 404) setErrorMsg('Strategy not loaded. Load strategy first via API.')
          else setErrorMsg((err as Error)?.message ?? 'Unexpected error.')
        },
      },
    )
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

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.6)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: 8, padding: '20px 24px', width: 320, boxShadow: '0 8px 32px rgba(0,0,0,.5)' }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16, color: 'var(--text-primary)' }}>Add Symbol</h3>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>Symbol</label>
            <input
              style={inputStyle}
              type="text"
              placeholder="e.g. BTC-USDT"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              onBlur={(e) => setSymbol(e.target.value.trim().toUpperCase())}
              autoFocus
            />
          </div>

          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>Exchange</label>
            <select style={inputStyle} value={exchange} onChange={(e) => setExchange(e.target.value)}>
              {EXCHANGES.map((ex) => <option key={ex} value={ex}>{ex}</option>)}
            </select>
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Interval</label>
            <select style={inputStyle} value={interval} onChange={(e) => setInterval(e.target.value)}>
              {INTERVALS.map((iv) => <option key={iv} value={iv}>{iv}</option>)}
            </select>
          </div>

          {errorMsg && (
            <div style={{ marginBottom: 12, padding: '6px 10px', background: 'rgba(239,83,80,.1)', border: '1px solid rgba(239,83,80,.3)', borderRadius: 4, color: '#ef5350', fontSize: 12 }}>
              {errorMsg}
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button type="button" className="btn" onClick={onClose}>Cancel</button>
            <button
              type="submit"
              className="btn-sm"
              disabled={addSymbol.isPending}
              style={{ minWidth: 64 }}
            >
              {addSymbol.isPending ? 'Adding…' : 'Add'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
