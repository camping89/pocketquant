import { useEffect, useMemo, useRef, useState } from 'react'
import { useAvailableIntervals } from '../../hooks/use-available-intervals'
import { useStrategyTrades } from '../../hooks/use-strategy-trades'
import { useSubscriptionAction } from '../../hooks/use-strategy-mutations'
import { useSubscriptionOrders, useSubscriptionSnapshot } from '../../hooks/use-subscription-detail'
import { moneyHint } from '../../lib/money-hint'
import {
  decisionText,
  errorText,
  manualActionText,
  pendingText,
  positionText,
  timeline,
} from '../../lib/subscription-view'
import { useFmt } from '../../lib/use-timezone'
import { IndicatorToggles } from '../controls/indicator-toggles'
import { IntervalSelector } from '../controls/interval-selector'
import { PnlBadge } from './pnl-badge'
import { ConfirmDialog } from './start-stop-button'
import { StrategyChart } from './strategy-chart'
import type { ManualAction, Subscription } from '../../api/strategy-api'
import type { Interval, IndicatorConfig } from '../../types/market-data'
import type { OpenPosition, Trade } from '../../types/strategy'

interface SubscriptionDrawerProps {
  sub: Subscription
  onClose: () => void
}

const INDICATORS_STORAGE_KEY = 'strategies.indicators'

const DEFAULT_INDICATORS: IndicatorConfig = {
  sma: false,
  ema: true,
  rsi: false,
  macd: false,
  bollinger: false,
  engulfing: true,
}

function readStoredIndicators(): IndicatorConfig {
  try {
    const raw = localStorage.getItem(INDICATORS_STORAGE_KEY)
    if (raw) return { ...DEFAULT_INDICATORS, ...JSON.parse(raw) }
  } catch { /* fall through to default */ }
  return DEFAULT_INDICATORS
}

function readingValue(v: unknown): string {
  if (v == null) return '-'
  return typeof v === 'string' ? v : JSON.stringify(v)
}

const cellStyle: React.CSSProperties = {
  padding: '3px 6px',
  borderBottom: '1px solid var(--border-color)',
  fontSize: 12,
  textAlign: 'left',
}

const headingStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  margin: '0 0 6px',
}

const ACTION_WORDS: Record<ManualAction, { button: string; real: string; paper: string }> = {
  cancel: {
    button: 'Cancel pending',
    real: 'This cancels a real-money order on Exness.',
    paper: 'This cancels a paper order.',
  },
  close: {
    button: 'Close at market',
    real: 'This closes a real-money position on Exness at market and cancels its pending order.',
    paper: 'This closes a paper position at market and cancels its pending order.',
  },
}

export function SubscriptionDrawer({ sub, onClose }: SubscriptionDrawerProps) {
  const fmt = useFmt()
  const closeRef = useRef<HTMLButtonElement>(null)
  const snapshot = sub.snapshot
  const pending = snapshot?.pending ?? null

  const ringQuery = useSubscriptionSnapshot(sub.id)
  const ordersQuery = useSubscriptionOrders(sub.id)
  const tradesQuery = useStrategyTrades(sub.id)
  const actionMut = useSubscriptionAction()
  const [confirm, setConfirm] = useState<ManualAction | null>(null)

  const [chartInterval, setChartInterval] = useState<Interval>(sub.intervals[0] as Interval)
  const intervalOptions = useAvailableIntervals(sub.symbol).filter((o) => sub.intervals.includes(o.value))
  const [indicators, setIndicators] = useState<IndicatorConfig>(readStoredIndicators)

  useEffect(() => {
    closeRef.current?.focus()
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && !confirm) onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose, confirm])

  function handleIndicatorsChange(next: IndicatorConfig) {
    setIndicators(next)
    try { localStorage.setItem(INDICATORS_STORAGE_KEY, JSON.stringify(next)) } catch { /* swallow */ }
  }

  const rawTrades = tradesQuery.data
  const trades = useMemo<Trade[]>(() => {
    const result: Trade[] = []
    for (const t of rawTrades ?? []) {
      const side = t.direction.toLowerCase() as 'long' | 'short'
      result.push({ timestamp: t.entry_time, side, is_entry: true, qty: t.quantity, price: t.entry_price })
      if (t.exit_time && t.exit_price != null) {
        result.push({ timestamp: t.exit_time, side, is_entry: false, qty: t.quantity, price: t.exit_price })
      }
    }
    return result
  }, [rawTrades])

  const position = sub.position
  const chartPosition = useMemo<OpenPosition | null>(() => {
    if (!position) return null
    return {
      side: position.direction.toLowerCase() as 'long' | 'short',
      entry_price: position.entry_price,
      liq_price: null,
      leverage: 1,
      qty: position.quantity,
    }
  }, [position])

  const recent = [...(ringQuery.data ?? [])].reverse()
  const events = timeline(ordersQuery.data ?? [], rawTrades ?? [])
  const actionText = manualActionText(sub.manual_action, sub.manual_action_outcome)
  const queued = sub.manual_action !== null
  const live = sub.broker === 'exness'
  const confirmHint = confirm ? moneyHint(sub.broker, confirm) : null
  // The polled row may drop the position or pending order while the confirm is open.
  if (confirm && (queued || (confirm === 'close' ? !position : !pending))) setConfirm(null)

  const actionButton = (action: ManualAction, enabled: boolean) => {
    const hint = moneyHint(sub.broker, action)
    return (
      <button
        type="button"
        className="btn btn-danger"
        disabled={!enabled || queued || actionMut.isPending}
        title={hint.title}
        onClick={() => { actionMut.reset(); setConfirm(action) }}
        style={{ padding: '3px 10px', fontSize: 12 }}
      >
        {ACTION_WORDS[action].button}
      </button>
    )
  }

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} aria-hidden />
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label={`Subscription ${sub.symbol}`}
        style={{ width: 'min(720px, 100vw)' }}
      >
        <header className="drawer-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>
              {sub.strategy_code} · {sub.symbol} · {sub.intervals.join(' ')}
            </span>
            <span className={`mode ${live ? 'mode-live' : 'mode-paper'}`}>{live ? 'LIVE' : 'PAPER'}</span>
            <span className={`state-pill state-pill--${sub.actual_state}`}>{sub.actual_state.toUpperCase()}</span>
          </div>
          <button type="button" ref={closeRef} className="drawer-close" onClick={onClose} aria-label="Close">×</button>
        </header>

        <section className="drawer-section">
          <h4 style={headingStyle}>Readings</h4>
          {!snapshot || snapshot.readings.length === 0 ? (
            <div className="empty-state" style={{ padding: 8 }}>No readings yet.</div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={cellStyle}>Interval</th>
                  <th style={cellStyle}>Name</th>
                  <th style={cellStyle}>Value</th>
                  <th style={cellStyle}>OK</th>
                </tr>
              </thead>
              <tbody>
                {snapshot.readings.map((r) => (
                  <tr key={`${r.interval}-${r.name}`}>
                    <td style={cellStyle}>{r.interval}</td>
                    <td style={cellStyle}>{r.name}</td>
                    <td style={{ ...cellStyle, fontVariantNumeric: 'tabular-nums' }}>{readingValue(r.value)}</td>
                    <td style={cellStyle}>{r.ok === true ? '✔' : r.ok === false ? '✘' : '–'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="drawer-section">
          <h4 style={headingStyle}>Decision</h4>
          <div>
            {decisionText(snapshot)}
            {snapshot && (
              <span style={{ color: 'var(--text-secondary)', fontSize: 11 }}>
                {' '}bar {fmt.format(snapshot.bar_start, 'YYYY-MM-DD HH:mm')}
                {snapshot.interval !== null && ` (${snapshot.interval})`}
              </span>
            )}
          </div>
        </section>

        <section className="drawer-section">
          <h4 style={headingStyle}>Pending order</h4>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'space-between' }}>
            <span>{pendingText(pending)}</span>
            {actionButton('cancel', pending !== null)}
          </div>
        </section>

        <section className="drawer-section">
          <h4 style={headingStyle}>Open position</h4>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'space-between' }}>
            <span>{positionText(position)}</span>
            {actionButton('close', position !== null)}
          </div>
          {position && (
            <div style={{ marginTop: 6 }}>
              <PnlBadge pnl={position.unrealized_pnl} />
            </div>
          )}
        </section>

        {actionText && (
          <div
            style={{
              fontSize: 12,
              color: !queued && sub.manual_action_outcome?.outcome.startsWith('rejected:')
                ? '#ef5350'
                : 'var(--text-secondary)',
            }}
          >
            {actionText}
          </div>
        )}
        {actionMut.error && <div className="drawer-error" style={{ marginTop: 8 }}>{errorText(actionMut.error)}</div>}

        <section className="drawer-section">
          <h4 style={headingStyle}>Recent decisions</h4>
          {ringQuery.error && <div className="drawer-error">{errorText(ringQuery.error)}</div>}
          {recent.length === 0 ? (
            <div className="empty-state" style={{ padding: 8 }}>No decisions yet.</div>
          ) : (
            recent.map((e, i) => (
              <div key={`${e.bar_start}-${i}`} style={{ fontSize: 12, padding: '2px 0' }}>
                <span style={{ color: 'var(--text-secondary)' }}>{fmt.format(e.bar_start, 'HH:mm')}</span>{' '}
                {decisionText(e)}
              </div>
            ))
          )}
        </section>

        <section className="drawer-section">
          <h4 style={headingStyle}>Orders &amp; trades</h4>
          {ordersQuery.error && <div className="drawer-error">{errorText(ordersQuery.error)}</div>}
          {tradesQuery.error && <div className="drawer-error">{errorText(tradesQuery.error)}</div>}
          {events.length === 0 ? (
            <div className="empty-state" style={{ padding: 8 }}>No orders or trades yet.</div>
          ) : (
            events.map((e, i) => (
              <div key={`${e.at}-${i}`} style={{ fontSize: 12, padding: '2px 0', borderBottom: '1px solid var(--border-color)' }}>
                <span style={{ color: 'var(--text-secondary)' }}>{fmt.format(e.at, 'MM-DD HH:mm')}</span>{' '}
                {e.text}
              </div>
            ))
          )}
        </section>

        <section className="drawer-section">
          <h4 style={headingStyle}>Chart</h4>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
            <IntervalSelector intervals={intervalOptions} value={chartInterval} onChange={setChartInterval} />
            <IndicatorToggles value={indicators} onChange={handleIndicatorsChange} />
          </div>
          <div style={{ height: 360 }}>
            <StrategyChart
              symbol={sub.symbol}
              interval={chartInterval}
              trades={trades}
              openPosition={chartPosition}
              indicators={indicators}
            />
          </div>
        </section>

      </aside>

      {/* Outside the drawer: its transform would make it the containing block of this
          fixed overlay, so the dialog would scroll with the drawer content. */}
      {confirm && confirmHint && (
        <ConfirmDialog
          heading={live ? ACTION_WORDS[confirm].real : ACTION_WORDS[confirm].paper}
          chip={<span className={`risk ${confirmHint.real ? 'risk-real' : 'risk-paper'}`}>{confirmHint.chip}</span>}
          confirm={
            <button
              type="button"
              className="btn btn-danger"
              title={confirmHint.title}
              onClick={() => {
                setConfirm(null)
                actionMut.mutate({ id: sub.id, action: confirm })
              }}
            >
              {ACTION_WORDS[confirm].button}
            </button>
          }
          onCancel={() => setConfirm(null)}
        >
          <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 12, lineHeight: 1.5 }}>
            {confirm === 'close' ? positionText(position) : pendingText(pending)}
          </p>
        </ConfirmDialog>
      )}
    </>
  )
}
