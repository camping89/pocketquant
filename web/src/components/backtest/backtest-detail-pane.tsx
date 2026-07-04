import { BacktestResultView } from './backtest-result-view'
import { BacktestStatusBadge } from '../strategy/backtest-status-badge'
import { useBacktestRun } from '../../hooks/use-backtest-run'

const pct = (n: number | undefined | null) => (n == null ? '—' : (n * 100).toFixed(1) + '%')

/** Detail pane of the workbench. Lazy: `useBacktestRun` is gated by `enabled`,
 *  so nothing is fetched until a run is selected (`runId` non-null). */
export function BacktestDetailPane({
  runId,
  activeTab,
  onTabChange,
}: {
  runId: string | null
  activeTab?: string
  onTabChange: (tab: string) => void
}) {
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
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <BacktestStatusBadge status={status ?? 'started'} errorMsg={errorMsg} />
        <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontFamily: 'monospace' }}>RunId: {runId}</span>
        {run && (
          <span style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span>–</span>
            <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{run.strategy_code}</span>
            <span>{[run.symbol, run.interval].filter(Boolean).join(' · ')}</span>
            {run.metrics && (
              <>
                <span style={{ color: run.metrics.total_return >= 0 ? 'var(--up-color)' : 'var(--down-color)' }}>
                  {pct(run.metrics.total_return)}
                </span>
                <span>SR {run.metrics.sharpe_ratio.toFixed(2)}</span>
                <span>{run.metrics.total_trades} trades</span>
              </>
            )}
            {run.verdict && <span title={run.verdict}>· {run.verdict}</span>}
          </span>
        )}
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

      {status === 'finished' && run && (
        <BacktestResultView run={run} runId={runId} activeTab={activeTab} onTabChange={onTabChange} />
      )}
    </div>
  )
}
