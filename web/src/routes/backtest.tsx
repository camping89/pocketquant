/* eslint-disable react-refresh/only-export-components -- TanStack Router requires Route export alongside components */
import { createFileRoute } from '@tanstack/react-router'
import { BacktestForm } from '../components/backtest/backtest-form'
import { RunHistoryRail } from '../components/backtest/run-history-rail'
import { useRunBacktest } from '../hooks/use-backtest-run'

export const Route = createFileRoute('/backtest')({
  component: BacktestPage,
})

function BacktestPage() {
  const runBacktest = useRunBacktest()

  return (
    <div style={{ maxWidth: 720, margin: '0 auto', padding: '24px 16px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <h1 style={{ fontSize: 18, fontWeight: 600, color: 'var(--text-primary)' }}>Backtest</h1>

      <section style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: 8, padding: 20 }}>
        <BacktestForm submitting={runBacktest.isPending} onSubmit={(body) => runBacktest.mutate(body)} />
        {runBacktest.isError && (
          <div style={{ marginTop: 12, padding: '6px 10px', background: 'rgba(239,83,80,.1)', border: '1px solid rgba(239,83,80,.3)', borderRadius: 4, color: '#ef5350', fontSize: 12 }}>
            {(runBacktest.error as Error)?.message ?? 'Failed to start backtest.'}
          </div>
        )}
      </section>

      <RunHistoryRail />
    </div>
  )
}
