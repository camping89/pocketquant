/**
 * Center bottom panel showing symbol/interval/template params for the
 * selected subscription. Read-only when running, editable when idle.
 */
import { parseSymbol } from '../../lib/symbol-format'
import { StartStopButton } from './start-stop-button'
import { useStartStrategy, useStopStrategy } from '../../hooks/use-strategy-mutations'
import type { Subscription } from '../../api/strategy-api'

interface StrategyConfigCardProps {
  sub: Subscription
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

export function StrategyConfigCard({ sub }: StrategyConfigCardProps) {
  const { code, exchange } = parseSymbol(sub.symbol)
  const isRunning = sub.backtest?.status === 'running'

  const startMut = useStartStrategy()
  const stopMut = useStopStrategy()

  const isLoading = startMut.isPending || stopMut.isPending

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
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
          Subscription Config
        </span>
        <StartStopButton
          isRunning={isRunning}
          isLoading={isLoading}
          onStart={() => startMut.mutate(sub.strategy_id)}
          onStop={() => stopMut.mutate(sub.strategy_id)}
        />
      </div>

      {/* Config rows */}
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
        <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{sub.strategy_id}</span>
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

      {/* Mutation error feedback */}
      {(startMut.isError || stopMut.isError) && (
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
          {((startMut.error ?? stopMut.error) as Error)?.message ?? 'Action failed'}
          {' — endpoint may not be available yet.'}
        </div>
      )}
    </div>
  )
}
