import { BacktestResultView } from './backtest-result-view'
import { BacktestStatusBadge } from '../strategy/backtest-status-badge'
import { useBacktestRun } from '../../hooks/use-backtest-run'

/** Detail pane of the workbench. Lazy: `useBacktestRun` is gated by `enabled`,
 *  so nothing is fetched until a run is selected (`runId` non-null). */
export function BacktestDetailPane({ runId }: { runId: string | null }) {
  const { data: run, isLoading } = useBacktestRun(runId)

  if (!runId) {
    return (
      <div
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--text-secondary)',
          fontSize: 13,
        }}
      >
        Select a run from the list.
      </div>
    )
  }

  const status = run?.status
  const errorMsg = run?.error_message ?? null

  return (
    <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
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
