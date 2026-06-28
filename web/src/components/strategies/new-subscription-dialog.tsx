/**
 * Modal dialog for creating a new strategy subscription.
 * Symbol selector + interval picker + strategy template selector + submit.
 */
import { useMemo, useState, type FormEvent } from 'react'
import { useStrategiesList } from '../../hooks/use-strategies'
import { useCreateSubscription } from '../../hooks/use-strategy-mutations'
import { useSymbols } from '../../hooks/use-symbols'
import { parseSymbol } from '../../lib/symbol-format'

const INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d']

interface NewSubscriptionDialogProps {
  onClose: () => void
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

export function NewSubscriptionDialog({ onClose }: NewSubscriptionDialogProps) {
  const { data: strategies, isLoading: strategiesLoading } = useStrategiesList()
  const { data: symbols, isLoading: symbolsLoading } = useSymbols()

  const activeSymbols = useMemo(
    () => symbols?.filter((s) => s.is_active) ?? [],
    [symbols],
  )

  const [strategyId, setStrategyId] = useState('')
  const [symbolInput, setSymbolInput] = useState('')
  const [interval, setInterval] = useState('1h')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // Derive effective symbol: user selection wins, otherwise first active.
  const symbol = symbolInput || activeSymbols[0]?.symbol || ''

  const createSub = useCreateSubscription(strategyId || null)

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setErrorMsg(null)

    if (!strategyId) { setErrorMsg('Select a strategy template.'); return }
    if (!symbol) { setErrorMsg('Select a symbol.'); return }

    createSub.mutate(
      { symbol, interval },
      {
        onSuccess: () => onClose(),
        onError: (err: unknown) => {
          const { code, message } = err as { code?: string; message?: string }
          if (code === 'SUBSCRIPTION_ALREADY_EXISTS')
            setErrorMsg('Subscription already exists for this symbol/interval.')
          else if (code === 'SYMBOL_NOT_TRACKED')
            setErrorMsg('Symbol is not tracked. An admin must add it to tracked symbols first.')
          else setErrorMsg(message ?? 'Unexpected error.')
        },
      },
    )
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,.65)',
        zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        style={{
          background: 'var(--bg-secondary)',
          border: '1px solid var(--border-color)',
          borderRadius: 8,
          padding: '20px 24px',
          width: 360,
          boxShadow: '0 8px 32px rgba(0,0,0,.55)',
        }}
      >
        <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 18, color: 'var(--text-primary)' }}>
          New Subscription
        </h3>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>Strategy Template</label>
            <select
              style={inputStyle}
              value={strategyId}
              onChange={(e) => setStrategyId(e.target.value)}
              disabled={strategiesLoading}
            >
              <option value="">
                {strategiesLoading ? 'Loading…' : '— Select strategy —'}
              </option>
              {strategies?.map((id) => (
                <option key={id} value={id}>{id}</option>
              ))}
            </select>
          </div>

          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>Symbol</label>
            <select
              style={inputStyle}
              value={symbol}
              onChange={(e) => setSymbolInput(e.target.value)}
              disabled={symbolsLoading || activeSymbols.length === 0}
              autoFocus
            >
              {symbolsLoading ? (
                <option value="">Loading…</option>
              ) : activeSymbols.length === 0 ? (
                <option value="">No active symbols</option>
              ) : (
                activeSymbols.map((s) => {
                  const { code, exchange } = parseSymbol(s.symbol)
                  const label = exchange ? `${code} — ${exchange}` : code
                  return (
                    <option key={s.symbol} value={s.symbol}>
                      {label}
                    </option>
                  )
                })
              )}
            </select>
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Interval</label>
            <div className="interval-group">
              {INTERVALS.map((iv) => (
                <button
                  key={iv}
                  type="button"
                  className={`interval-btn${interval === iv ? ' active' : ''}`}
                  onClick={() => setInterval(iv)}
                >
                  {iv}
                </button>
              ))}
            </div>
          </div>

          {errorMsg && (
            <div
              style={{
                marginBottom: 12, padding: '6px 10px',
                background: 'rgba(239,83,80,.1)', border: '1px solid rgba(239,83,80,.3)',
                borderRadius: 4, color: '#ef5350', fontSize: 12,
              }}
            >
              {errorMsg}
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button type="button" className="btn" onClick={onClose}>Cancel</button>
            <button
              type="submit"
              className="btn-sm"
              disabled={createSub.isPending}
              style={{ minWidth: 80 }}
            >
              {createSub.isPending ? 'Creating…' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
