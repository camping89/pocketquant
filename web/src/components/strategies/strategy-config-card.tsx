import { parseSymbol } from '../../lib/symbol-format'
import { moneyHint } from '../../lib/money-hint'
import { StartStopButton } from './start-stop-button'
import {
  useStartStrategy,
  useStopStrategy,
  useDeleteSubscription,
} from '../../hooks/use-strategy-mutations'
import type { Subscription } from '../../api/strategy-api'

interface StrategyConfigCardProps {
  sub: Subscription
  onDeleted?: () => void
}

const rowStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '6px 0',
  borderBottom: '1px solid var(--border-color)',
  fontSize: 13,
}

const labelStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
}

// Delete sits alone in the footer so no two red buttons share a group.
export function StrategyConfigCard({ sub, onDeleted }: StrategyConfigCardProps) {
  const { code, exchange } = parseSymbol(sub.symbol)
  const isRunning = sub.is_running

  const startMut = useStartStrategy()
  const stopMut = useStopStrategy()
  const deleteMut = useDeleteSubscription()

  const isLoading = startMut.isPending || stopMut.isPending || deleteMut.isPending
  const runHint = moneyHint(sub.broker, isRunning ? 'stop' : 'start')
  const deleteHint = moneyHint(sub.broker, 'delete')

  function handleDelete() {
    if (isRunning) return
    const confirmed = window.confirm(
      `Delete subscription ${code}${exchange ? ` (${exchange})` : ''} · ${sub.interval} · ${sub.strategy_code}?`,
    )
    if (!confirmed) return
    deleteMut.mutate(sub.id, { onSuccess: () => onDeleted?.() })
  }

  return (
    <div
      style={{
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border-color)',
        borderRadius: 6,
        padding: '12px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 0,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
          Subscription Config
        </span>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span className={`risk ${runHint.real ? 'risk-real' : 'risk-paper'}`} title={runHint.title}>
            {runHint.chip}
          </span>
          <StartStopButton
            isRunning={isRunning}
            isLoading={isLoading}
            onStart={() => startMut.mutate(sub.id)}
            onStop={() => stopMut.mutate(sub.id)}
            broker={sub.broker}
            label={`${code} · ${sub.interval}`}
          />
        </div>
      </div>

      <div style={rowStyle}>
        <span style={labelStyle}>Symbol</span>
        <span style={{ fontWeight: 600 }}>{code}</span>
      </div>

      {exchange && (
        <div style={rowStyle}>
          <span style={labelStyle}>Exchange</span>
          <span
            style={{
              fontSize: 11,
              fontWeight: 600,
              padding: '1px 6px',
              borderRadius: 3,
              background: 'rgba(96,125,139,0.2)',
              color: '#90a4ae',
              textTransform: 'uppercase',
            }}
          >
            {exchange}
          </span>
        </div>
      )}

      <div style={rowStyle}>
        <span style={labelStyle}>Interval</span>
        <span>{sub.interval}</span>
      </div>

      <div style={rowStyle}>
        <span style={labelStyle}>Strategy</span>
        <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{sub.strategy_code}</span>
      </div>

      <div style={{ ...rowStyle, borderBottom: 'none' }}>
        <span style={labelStyle}>Sub ID</span>
        <span
          style={{
            fontSize: 11,
            fontFamily: 'monospace',
            color: 'var(--text-secondary)',
            maxWidth: 160,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
          title={sub.id}
        >
          {sub.id}
        </span>
      </div>

      <div
        style={{
          display: 'flex',
          justifyContent: 'flex-end',
          alignItems: 'center',
          gap: 6,
          paddingTop: 10,
          marginTop: 4,
          borderTop: '1px solid var(--border-color)',
        }}
      >
        <span className={`risk ${deleteHint.real ? 'risk-real' : 'risk-paper'}`} title={deleteHint.title}>
          {deleteHint.chip}
        </span>
        <button
          type="button"
          className="btn btn-danger"
          onClick={handleDelete}
          disabled={isLoading || isRunning}
          title={isRunning ? 'Stop the strategy before deleting' : deleteHint.title}
        >
          {deleteMut.isPending ? 'Deleting…' : 'Delete'}
        </button>
      </div>

      {(startMut.isError || stopMut.isError || deleteMut.isError) && (
        <div
          style={{
            marginTop: 10,
            padding: '6px 10px',
            background: 'rgba(239,83,80,.1)',
            border: '1px solid rgba(239,83,80,.3)',
            borderRadius: 4,
            color: '#ef5350',
            fontSize: 11,
          }}
        >
          {((startMut.error ?? stopMut.error ?? deleteMut.error) as Error)?.message ?? 'Action failed'}
        </div>
      )}
    </div>
  )
}
