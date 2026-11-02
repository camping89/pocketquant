import { useState } from 'react'
import { parseSymbol } from '../../lib/symbol-format'
import { moneyHint } from '../../lib/money-hint'
import {
  decisionText,
  errorText,
  manualActionText,
  pendingText,
  positionText,
} from '../../lib/subscription-view'
import {
  useDeleteSubscription,
  useStartStrategy,
  useStopStrategy,
} from '../../hooks/use-strategy-mutations'
import { ConfirmDialog, StartStopButton } from './start-stop-button'
import type { Subscription } from '../../api/strategy-api'

interface StrategyCardProps {
  sub: Subscription
  selected: boolean
  onOpen: () => void
  onEdit: () => void
}

type RowState = 'running' | 'starting' | 'stopped'

function toRowState(sub: Subscription): RowState {
  if (sub.actual_state === 'running') return 'running'
  if (sub.desired_state === 'running') return 'starting'  // converging
  return 'stopped'
}

const lineStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  flexWrap: 'wrap',
  fontSize: 11,
  color: 'var(--text-secondary)',
  marginTop: 2,
}

export function StrategyCard({ sub, selected, onOpen, onEdit }: StrategyCardProps) {
  const { code, exchange } = parseSymbol(sub.symbol)
  const state = toRowState(sub)
  const live = sub.broker === 'exness'
  const stopped = sub.desired_state === 'stopped' && sub.actual_state === 'stopped'
  const pending = sub.snapshot?.pending ?? null
  const actionText = manualActionText(sub.manual_action, sub.manual_action_outcome)
  const deleteHint = moneyHint(sub.broker, 'delete')

  const startMut = useStartStrategy()
  const stopMut = useStopStrategy()
  const deleteMut = useDeleteSubscription()
  const [confirmDelete, setConfirmDelete] = useState(false)
  // Deleting a starting subscription would race the reconcile loop, so both states must be stopped.
  if (confirmDelete && !stopped) setConfirmDelete(false)
  const isLoading = startMut.isPending || stopMut.isPending || deleteMut.isPending
  const error = startMut.error ?? stopMut.error ?? deleteMut.error
  const resetErrors = () => { startMut.reset(); stopMut.reset(); deleteMut.reset() }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault()
          onOpen()
        }
      }}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        width: '100%',
        padding: '8px 12px',
        background: selected ? 'rgba(38,166,154,0.10)' : 'transparent',
        borderLeft: `3px solid ${selected ? 'var(--accent)' : 'transparent'}`,
        borderBottom: '1px solid var(--border-color)',
        cursor: 'pointer',
        textAlign: 'left',
        transition: 'background 0.12s',
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
            {code}
          </span>
          {exchange && (
            <span
              style={{
                fontSize: 10,
                fontWeight: 600,
                padding: '1px 5px',
                borderRadius: 3,
                background: 'rgba(96,125,139,0.2)',
                color: '#90a4ae',
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
              }}
            >
              {exchange}
            </span>
          )}
          <span className={`mode ${live ? 'mode-live' : 'mode-paper'}`} title={`broker: ${sub.broker}`}>
            {live ? 'LIVE' : 'PAPER'}
          </span>
          {sub.intervals.map((iv, i) => (
            <span
              key={iv}
              className="interval-btn active"
              title={i === 0 ? 'entry interval' : undefined}
              style={{ fontSize: 10, padding: '0 5px', fontWeight: i === 0 ? 700 : 400, cursor: 'inherit' }}
            >
              {iv}
            </span>
          ))}
          <span className={`state-pill state-pill--${state}`}>{state.toUpperCase()}</span>
          <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{sub.strategy_code}</span>
        </div>
        <div style={lineStyle}>
          {positionText(sub.position)} · {pendingText(pending)} · {decisionText(sub.snapshot)}
        </div>
        {actionText && (
          <div
            style={{
              ...lineStyle,
              color: sub.manual_action_outcome?.outcome.startsWith('rejected:') && !sub.manual_action
                ? '#ef5350'
                : lineStyle.color,
            }}
          >
            {actionText}
          </div>
        )}
        {error && <div style={{ ...lineStyle, color: '#ef5350' }}>{errorText(error)}</div>}
      </div>

      <div
        style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
      >
        <StartStopButton
          isRunning={sub.is_running}
          isLoading={isLoading}
          onStart={() => { resetErrors(); startMut.mutate(sub.id) }}
          onStop={() => { resetErrors(); stopMut.mutate(sub.id) }}
          broker={sub.broker}
          label={`${code} · ${sub.intervals.join(' ')}`}
        />
        <button
          type="button"
          className="btn"
          disabled={!stopped}
          title={stopped ? 'Edit intervals and parameters' : 'Stop the subscription before editing'}
          onClick={onEdit}
          style={{ padding: '4px 10px', fontSize: 12 }}
        >
          Edit
        </button>
        <button
          type="button"
          className="btn btn-danger"
          disabled={isLoading || !stopped}
          title={stopped ? deleteHint.title : 'Stop the strategy before deleting'}
          onClick={() => setConfirmDelete(true)}
          style={{ padding: '4px 10px', fontSize: 12 }}
        >
          {deleteMut.isPending ? 'Deleting…' : 'Delete'}
        </button>

        {confirmDelete && (
          <ConfirmDialog
            heading={`Delete ${code} · ${sub.intervals.join(' ')} · ${sub.strategy_code}?`}
            chip={<span className={`risk ${deleteHint.real ? 'risk-real' : 'risk-paper'}`}>{deleteHint.chip}</span>}
            confirm={
              <button
                type="button"
                className="btn btn-danger"
                title={deleteHint.title}
                onClick={() => { setConfirmDelete(false); resetErrors(); deleteMut.mutate(sub.id) }}
              >
                Delete
              </button>
            }
            onCancel={() => setConfirmDelete(false)}
          >
            {(sub.position || pending) && (
              <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 12, lineHeight: 1.5 }}>
                This subscription still has {positionText(sub.position)} / {pendingText(pending)}. Deleting it does not close them.
              </p>
            )}
          </ConfirmDialog>
        )}
      </div>
    </div>
  )
}
