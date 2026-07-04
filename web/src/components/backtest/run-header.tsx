import { useState } from 'react'
import type { BacktestMetrics } from '../../api/backtest-api'
import { BacktestStatusBadge } from '../strategy/backtest-status-badge'

interface RunHeaderProps {
  runId: string
  status: string
  errorMsg: string | null
  strategyCode?: string
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

/** At-a-glance run summary: identity row (status · strategy · symbol · runId)
 *  above scannable metric tiles. The full verdict lives in its own card, so it
 *  is deliberately NOT crammed into this header. */
export function RunHeader({ runId, status, errorMsg, strategyCode, symbol, interval, metrics }: RunHeaderProps) {
  const [copied, setCopied] = useState(false)

  function copyRunId() {
    void navigator.clipboard?.writeText(runId).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1200)
    })
  }

  const pair = [symbol, interval].filter(Boolean).join(' · ')

  return (
    <header className="run-detail-header">
      <div className="run-detail-header__identity">
        <BacktestStatusBadge status={status} errorMsg={errorMsg} />
        {strategyCode && <span className="run-detail-header__title">{strategyCode}</span>}
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
