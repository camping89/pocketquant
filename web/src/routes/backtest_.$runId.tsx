/* eslint-disable react-refresh/only-export-components -- TanStack Router requires Route export alongside components */
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { BacktestResultView } from '../components/backtest/backtest-result-view'
import { BacktestStatusBadge } from '../components/strategy/backtest-status-badge'
import { useBacktestRun } from '../hooks/use-backtest-run'

export const Route = createFileRoute('/backtest_/$runId')({
  component: BacktestDetailPage,
})

function BacktestDetailPage() {
  const { runId } = Route.useParams()
  const navigate = useNavigate()
  const { data: run, isLoading } = useBacktestRun(runId)

  const status = run?.status
  const errorMsg = run?.error_message ?? null

  return (
    <div style={{ maxWidth: 1080, margin: '0 auto', padding: '24px 16px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <button type="button" className="btn-sm" onClick={() => void navigate({ to: '/backtest' })}>
          ← Backtest
        </button>
        <BacktestStatusBadge status={status ?? 'started'} errorMsg={errorMsg} />
        <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontFamily: 'monospace' }}>{runId}</span>
      </div>

      {(isLoading || status === 'started') && (
        <div className="empty-state" style={{ padding: 24, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
          <div className="loading-spinner" />
          <div>Running backtest…</div>
        </div>
      )}

      {status === 'failed' && (
        <div className="empty-state empty-state--error" style={{ padding: 24 }}>
          <div>✗ Backtest failed</div>
          <div className="empty-state__sub">{errorMsg ?? 'Backtest engine error'}</div>
        </div>
      )}

      {status === 'finished' && run && <BacktestResultView run={run} runId={runId} />}
    </div>
  )
}
