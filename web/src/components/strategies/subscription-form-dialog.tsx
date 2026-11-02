import { useMemo, useState, type FormEvent } from 'react'
import { useStrategiesList, useStrategyDefaults } from '../../hooks/use-strategies'
import { useCreateSubscription, useEditSubscription } from '../../hooks/use-strategy-mutations'
import { useSafeguards } from '../../hooks/use-safeguards'
import { useSymbols } from '../../hooks/use-symbols'
import { parseSymbol } from '../../lib/symbol-format'
import { moneyHint, type Broker } from '../../lib/money-hint'
import { errorText, parseParameters } from '../../lib/subscription-view'
import { IntervalMultiSelect } from '../controls/interval-multi-select'
import { ParamsEditor } from '../controls/params-editor'
import type { Subscription } from '../../api/strategy-api'

interface SubscriptionFormDialogProps {
  // Given: edit this subscription. Absent: create a new one.
  sub?: Subscription
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

const noteStyle: React.CSSProperties = { fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }

const BROKERS: { value: Broker; label: string }[] = [
  { value: 'paper', label: 'PAPER' },
  { value: 'exness', label: 'LIVE' },
]

export function SubscriptionFormDialog({ sub, onClose }: SubscriptionFormDialogProps) {
  const editing = sub !== undefined
  const { data: strategies, isLoading: strategiesLoading } = useStrategiesList()
  const { data: symbols, isLoading: symbolsLoading } = useSymbols()
  const safeguards = useSafeguards()

  const activeSymbols = useMemo(
    () => symbols?.filter((s) => s.is_active) ?? [],
    [symbols],
  )

  const [strategyId, setStrategyId] = useState(sub?.strategy_code ?? '')
  const [symbolInput, setSymbolInput] = useState('')
  const [intervals, setIntervals] = useState<string[]>(sub?.intervals ?? ['1h'])
  const [chosenBroker, setBroker] = useState<Broker>(sub?.broker ?? 'paper')
  const [paramsText, setParamsText] = useState(sub ? JSON.stringify(sub.parameters, null, 2) : '')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // Derive effective symbol: user selection wins, otherwise first active.
  const symbol = sub?.symbol ?? (symbolInput || activeSymbols[0]?.symbol || '')

  // Create prefills parameters once per strategy from its declared defaults (adjust state
  // while rendering); edit keeps the subscription's own parameters.
  const defaults = useStrategyDefaults(strategyId)
  const [paramsFor, setParamsFor] = useState(sub?.strategy_code ?? '')
  if (defaults.data && paramsFor !== strategyId) {
    setParamsFor(strategyId)
    setParamsText(JSON.stringify(defaults.data, null, 2))
  }

  const createSub = useCreateSubscription(strategyId || null)
  const editSub = useEditSubscription()
  const pending = createSub.isPending || editSub.isPending
  const liveAllowed = safeguards.data?.live_trading === true
  // LIVE falls back to paper when the trader's live flag turns off after it was picked.
  const broker = liveAllowed ? chosenBroker : 'paper'
  const stopped = !sub || (sub.desired_state === 'stopped' && sub.actual_state === 'stopped')
  const hint = moneyHint(broker, 'start')

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setErrorMsg(null)

    const parsed = parseParameters(paramsText)
    if ('error' in parsed) { setErrorMsg(parsed.error); return }
    const onError = (err: unknown) => setErrorMsg(errorText(err))

    if (sub) {
      editSub.mutate(
        { id: sub.id, intervals, parameters: parsed.value },
        { onSuccess: () => onClose(), onError },
      )
      return
    }
    if (!strategyId) { setErrorMsg('Select a strategy template.'); return }
    if (!symbol) { setErrorMsg('Select a symbol.'); return }
    createSub.mutate(
      { symbol, intervals, parameters: parsed.value, broker },
      { onSuccess: () => onClose(), onError },
    )
  }

  const readOnly = (label: string, value: string) => (
    <div style={{ marginBottom: 12 }}>
      <label style={labelStyle}>{label}</label>
      <div style={{ fontSize: 13, color: 'var(--text-primary)' }}>{value}</div>
    </div>
  )

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
          width: 460,
          maxWidth: '100%',
          maxHeight: '90vh',
          overflowY: 'auto',
          boxShadow: '0 8px 32px rgba(0,0,0,.55)',
        }}
      >
        <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 18, color: 'var(--text-primary)' }}>
          {editing ? 'Edit subscription' : 'New subscription'}
        </h3>

        <form onSubmit={handleSubmit}>
          {sub ? (
            <>
              {readOnly('Strategy', sub.strategy_code)}
              {readOnly('Symbol', sub.symbol)}
              {readOnly('Broker', sub.broker === 'exness' ? 'LIVE' : 'PAPER')}
            </>
          ) : (
            <>
              <div style={{ marginBottom: 12 }}>
                <label style={labelStyle}>Strategy</label>
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

              <div style={{ marginBottom: 12 }}>
                <label style={labelStyle}>Broker</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div className="interval-group">
                    {BROKERS.map((b) => {
                      const disabled = b.value === 'exness' && !liveAllowed
                      return (
                        <button
                          type="button"
                          key={b.value}
                          className={`interval-btn ${broker === b.value ? 'active' : ''} ${disabled ? 'disabled' : ''}`}
                          disabled={disabled}
                          onClick={() => setBroker(b.value)}
                        >
                          {b.label}
                        </button>
                      )
                    })}
                  </div>
                  <span className={`risk ${hint.real ? 'risk-real' : 'risk-paper'}`} title={hint.title}>
                    {hint.chip}
                  </span>
                </div>
                {!liveAllowed && (
                  <div style={noteStyle}>LIVE places real-money orders and needs the trader's live flag on.</div>
                )}
              </div>
            </>
          )}

          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>Intervals</label>
            <IntervalMultiSelect value={intervals} onChange={setIntervals} />
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Parameters</label>
            <ParamsEditor defaults={defaults.data ?? {}} text={paramsText} onChange={setParamsText} />
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

          {!stopped && (
            <div style={{ ...noteStyle, marginBottom: 12 }}>
              Edit is enabled only while the subscription is stopped. Start re-runs warm-up.
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button type="button" className="btn" onClick={onClose}>Cancel</button>
            <button
              type="submit"
              className="btn-sm"
              disabled={pending || !stopped}
              style={{ minWidth: 80 }}
            >
              {editing
                ? (editSub.isPending ? 'Saving…' : 'Save')
                : (createSub.isPending ? 'Creating…' : 'Create (stopped)')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
