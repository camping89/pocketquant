/* eslint-disable react-refresh/only-export-components -- TanStack Router requires Route export alongside components */
import { useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { BacktestForm } from '../components/backtest/backtest-form'
import { BacktestResultView } from '../components/backtest/backtest-result-view'
import { BacktestStatusBadge } from '../components/strategy/backtest-status-badge'
import { useRunBacktest, useBacktestRun } from '../hooks/use-backtest-run'

export const Route = createFileRoute('/backtest')({
  component: BacktestPage,
})

function BacktestPage() {
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const runBacktest = useRunBacktest()
  const { data: run } = useBacktestRun(activeRunId)

  const status = run?.status
  const errorMsg = run?.error_message ?? run?.error_msg ?? null

  return (
    <div style={{ maxWidth: 720, margin: '0 auto', padding: '24px 16px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <h1 style={{ fontSize: 18, fontWeight: 600, color: 'var(--text-primary)' }}>Backtest</h1>

      <section style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: 8, padding: 20 }}>
        <BacktestForm
          submitting={runBacktest.isPending}
          onSubmit={(body) =>
            runBacktest.mutate(body, {
              onSuccess: ({ request_id }) => setActiveRunId(request_id),
            })
          }
        />
        {runBacktest.isError && (
          <div style={{ marginTop: 12, padding: '6px 10px', background: 'rgba(239,83,80,.1)', border: '1px solid rgba(239,83,80,.3)', borderRadius: 4, color: '#ef5350', fontSize: 12 }}>
            {(runBacktest.error as Error)?.message ?? 'Failed to start backtest.'}
          </div>
        )}
      </section>

      {activeRunId && (
        <section style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: 8, padding: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>Result</span>
            <BacktestStatusBadge status={status ?? 'started'} errorMsg={errorMsg} />
            <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontFamily: 'monospace' }}>{activeRunId}</span>
          </div>

          {(!run || status === 'started') && (
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

          {status === 'finished' && run && <BacktestResultView run={run} />}
        </section>
      )}
    </div>
  )
}
