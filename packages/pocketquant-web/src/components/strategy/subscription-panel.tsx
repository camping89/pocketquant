import { useState } from 'react'
import {
  useSubscriptions,
  useRunAllBacktests,
  useRemoveSymbol,
  useDeleteStrategy,
} from '../../hooks/use-subscriptions'
import { BacktestStatusBadge } from './backtest-status-badge'
import { AddSymbolDialog } from './add-symbol-dialog'
import type { Subscription } from '../../api/strategy-api'

interface SubscriptionPanelProps {
  strategyId: string | null
  selectedSubId: string | null
  onSelectSub: (subId: string | null) => void
}

function relTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const ms = Date.now() - new Date(iso).getTime()
  if (ms < 60_000) return `${Math.floor(ms / 1000)}s ago`
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m ago`
  if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)}h ago`
  return `${Math.floor(ms / 86_400_000)}d ago`
}

interface SubRowProps {
  sub: Subscription
  selected: boolean
  onSelect: () => void
  onRemove: () => void
  removing: boolean
}

function SubRow({ sub, selected, onSelect, onRemove, removing }: SubRowProps) {
  const bt = sub.backtest

  return (
    <div
      onClick={onSelect}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '7px 10px',
        cursor: 'pointer',
        borderBottom: '1px solid var(--border-color)',
        background: selected ? 'rgba(38,166,154,0.08)' : 'transparent',
        borderLeft: selected ? '2px solid var(--accent)' : '2px solid transparent',
        transition: 'background 0.12s',
      }}
    >
      <BacktestStatusBadge
        status={bt?.status ?? null}
        lastRunAt={bt?.last_run_at}
        errorMsg={bt?.error_msg}
      />
      <span style={{ flex: 1, fontSize: 12, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {sub.symbol} <span style={{ color: 'var(--text-secondary)' }}>• {sub.exchange.toLowerCase()} • {sub.interval}</span>
      </span>
      <span style={{ fontSize: 11, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
        {relTime(bt?.last_run_at)}
      </span>
      <button
        className="btn"
        title="Remove subscription"
        disabled={removing}
        onClick={(e) => { e.stopPropagation(); onRemove() }}
        style={{ padding: '1px 6px', fontSize: 13, lineHeight: 1, minWidth: 'unset', flexShrink: 0 }}
      >
        ×
      </button>
    </div>
  )
}

export function SubscriptionPanel({ strategyId, selectedSubId, onSelectSub }: SubscriptionPanelProps) {
  const [showDialog, setShowDialog] = useState(false)
  const { data: subs, isLoading } = useSubscriptions(strategyId)
  const runAll = useRunAllBacktests(strategyId)
  const removeSymbol = useRemoveSymbol(strategyId)
  const deleteStrat = useDeleteStrategy()

  if (!strategyId) {
    return (
      <div style={panelStyle}>
        <div style={{ color: 'var(--text-secondary)', fontSize: 12, padding: '12px 10px' }}>
          Select a strategy to manage subscriptions.
        </div>
      </div>
    )
  }

  const allRunning = subs?.every((s) => s.backtest?.status === 'running') ?? false
  const hasRunning = subs?.some((s) => s.backtest?.status === 'running') ?? false

  function handleRunAll() {
    runAll.mutate()
  }

  function handleDeleteStrategy() {
    if (!strategyId) return
    if (!window.confirm(`Delete strategy "${strategyId}" and all its subscriptions?`)) return
    deleteStrat.mutate(strategyId, {
      onSuccess: () => onSelectSub(null),
    })
  }

  function handleRemove(subId: string) {
    removeSymbol.mutate(subId, {
      onSuccess: () => { if (selectedSubId === subId) onSelectSub(null) },
    })
  }

  return (
    <div style={panelStyle}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 10px', borderBottom: '1px solid var(--border-color)', flexShrink: 0 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', flex: 1 }}>Symbols</span>
        <button className="btn-sm" onClick={() => setShowDialog(true)} style={{ padding: '2px 8px', fontSize: 11 }}>
          + Add
        </button>
        <button
          className="btn-sm"
          onClick={handleRunAll}
          disabled={!subs?.length || allRunning || hasRunning || runAll.isPending}
          style={{ padding: '2px 8px', fontSize: 11 }}
        >
          {runAll.isPending ? 'Starting…' : 'Run All'}
        </button>
        <button
          className="btn"
          onClick={handleDeleteStrategy}
          disabled={deleteStrat.isPending}
          title="Delete strategy and all subscriptions"
          style={{ padding: '2px 6px', fontSize: 11, color: '#ef5350', borderColor: 'rgba(239,83,80,.4)', flexShrink: 0 }}
        >
          {deleteStrat.isPending ? '…' : 'Del'}
        </button>
      </div>

      {/* List */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {isLoading && (
          <div style={{ padding: '12px 10px', fontSize: 12, color: 'var(--text-secondary)' }}>Loading…</div>
        )}
        {!isLoading && (!subs || subs.length === 0) && (
          <div style={{ padding: '12px 10px', fontSize: 12, color: 'var(--text-secondary)' }}>
            No symbols yet. Click + Add to subscribe.
          </div>
        )}
        {subs?.map((sub) => (
          <SubRow
            key={sub.id}
            sub={sub}
            selected={sub.id === selectedSubId}
            onSelect={() => onSelectSub(sub.id === selectedSubId ? null : sub.id)}
            onRemove={() => handleRemove(sub.id)}
            removing={removeSymbol.isPending && removeSymbol.variables === sub.id}
          />
        ))}
      </div>

      {showDialog && strategyId && (
        <AddSymbolDialog strategyId={strategyId} onClose={() => setShowDialog(false)} />
      )}
    </div>
  )
}

const panelStyle: React.CSSProperties = {
  width: 280,
  flexShrink: 0,
  display: 'flex',
  flexDirection: 'column',
  background: 'var(--bg-secondary)',
  borderRight: '1px solid var(--border-color)',
  overflow: 'hidden',
}
