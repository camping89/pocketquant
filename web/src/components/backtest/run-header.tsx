import { useState } from 'react'
import type { BacktestMetrics } from '../../api/backtest-api'
import { useSetBacktestName } from '../../hooks/use-backtest-run'
import { BacktestStatusBadge } from '../strategy/backtest-status-badge'

interface RunHeaderProps {
  runId: string
  status: string
  errorMsg: string | null
  strategyCode?: string
  name?: string | null
  symbol?: string
  interval?: string
  metrics: BacktestMetrics | null
}

const pct = (n: number | undefined | null) => (n == null ? '—' : (n * 100).toFixed(1) + '%')

type Tone = 'up' | 'down' | 'neutral'

function Stat({ label, value, tone = 'neutral' }: { label: string; value: string; tone?: Tone }) {
  const cls = tone === 'up' ? ' run-stat--up' : tone === 'down' ? ' run-stat--down' : ''
  return (
    <div className={`run-stat${cls}`}>
      <div className="run-stat__label">{label}</div>
      <div className="run-stat__value">{value}</div>
    </div>
  )
}

/** At-a-glance run summary: identity row (status · name/strategy · symbol · runId)
 *  above scannable metric tiles. The run label is inline-editable here; the full
 *  verdict lives in its own card, deliberately NOT crammed into this header. */
export function RunHeader({ runId, status, errorMsg, strategyCode, name, symbol, interval, metrics }: RunHeaderProps) {
  const [copied, setCopied] = useState(false)

  const canonicalName = name ?? ''
  const [nameText, setNameText] = useState(canonicalName)
  const [editingName, setEditingName] = useState(false)
  // Reset editor only when the route switches to a DIFFERENT run — optimistic
  // write + revert both flow through the `name` prop, so resetting on those
  // would clobber the user's text on a failed save. (Same pattern as VerdictPanel.)
  const [seenRunId, setSeenRunId] = useState(runId)
  if (seenRunId !== runId) {
    setSeenRunId(runId)
    setNameText(canonicalName)
    setEditingName(false)
  }

  const nameMutation = useSetBacktestName(runId)
  const nameDirty = nameText !== canonicalName

  function saveName() {
    nameMutation.mutate(nameText.trim() === '' ? null : nameText, {
      onSuccess: () => setEditingName(false),
    })
  }

  function cancelName() {
    setNameText(canonicalName)
    setEditingName(false)
    nameMutation.reset()
  }

  function copyRunId() {
    void navigator.clipboard?.writeText(runId).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1200)
    })
  }

  const pair = [symbol, interval].filter(Boolean).join(' · ')
  const title = canonicalName || strategyCode
  // Editing is post-run only: while a run is still ``started`` the engine's
  // finalize() rewrites the whole doc (replace_one) and would clobber a PATCHed
  // name with the creation-time value. Show the label, hide the editor until finished.
  const canEditName = status === 'finished'

  return (
    <header className="run-detail-header">
      <div className="run-detail-header__identity">
        <BacktestStatusBadge status={status} errorMsg={errorMsg} />
        {editingName && canEditName ? (
          <span className="run-detail-header__name-edit">
            <input
              className="run-detail-header__name-input"
              value={nameText}
              onChange={(e) => setNameText(e.target.value)}
              placeholder="Tên run…"
              maxLength={200}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter' && nameDirty && !nameMutation.isPending) saveName()
                if (e.key === 'Escape') cancelName()
              }}
            />
            <button type="button" className="btn-sm" onClick={cancelName} disabled={nameMutation.isPending}>
              Cancel
            </button>
            <button type="button" className="btn-sm" onClick={saveName} disabled={!nameDirty || nameMutation.isPending}>
              {nameMutation.isPending ? 'Saving…' : 'Save'}
            </button>
          </span>
        ) : (
          <>
            {title && <span className="run-detail-header__title">{title}</span>}
            {canonicalName && strategyCode && (
              <span className="run-detail-header__pair">{strategyCode}</span>
            )}
            {canEditName && (
              <button
                type="button"
                className="run-detail-header__copy"
                onClick={() => setEditingName(true)}
                title={canonicalName ? 'Edit name' : 'Add name'}
                aria-label={canonicalName ? 'Edit run name' : 'Add run name'}
              >
                {canonicalName ? '✎' : '+ name'}
              </button>
            )}
          </>
        )}
        {pair && <span className="run-detail-header__pair">{pair}</span>}
        <span className="run-detail-header__runid" title={runId}>
          <span>{runId.slice(0, 8)}…{runId.slice(-4)}</span>
          <button
            type="button"
            className="run-detail-header__copy"
            onClick={copyRunId}
            aria-label="Copy run id"
            title={copied ? 'Copied' : 'Copy run id'}
          >
            {copied ? '✓' : '⧉'}
          </button>
        </span>
      </div>

      {metrics && (
        <div className="run-stats">
          <Stat label="Return" value={pct(metrics.total_return)} tone={metrics.total_return >= 0 ? 'up' : 'down'} />
          <Stat label="Sharpe" value={metrics.sharpe_ratio.toFixed(2)} tone={metrics.sharpe_ratio >= 0 ? 'up' : 'down'} />
          <Stat label="Win%" value={pct(metrics.win_rate)} />
          <Stat label="Max DD" value={pct(metrics.max_drawdown)} tone={metrics.max_drawdown < 0 ? 'down' : 'neutral'} />
          <Stat label="Trades" value={metrics.total_trades.toLocaleString()} />
        </div>
      )}
    </header>
  )
}
