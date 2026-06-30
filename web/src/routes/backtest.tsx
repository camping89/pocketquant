/* eslint-disable react-refresh/only-export-components -- TanStack Router requires Route export alongside components */
import { createFileRoute } from '@tanstack/react-router'
import { BacktestWorkbench } from '../components/backtest/backtest-workbench'

export const Route = createFileRoute('/backtest')({
  validateSearch: (s: Record<string, unknown>): { run?: string } => ({
    run: typeof s.run === 'string' ? s.run : undefined,
  }),
  errorComponent: () => (
    <div className="empty-state empty-state--error" style={{ padding: 24 }}>
      <div>✗ Failed to render this view</div>
      <div className="empty-state__sub">Try selecting another run or reloading.</div>
    </div>
  ),
  component: BacktestPage,
})

function BacktestPage() {
  const { run } = Route.useSearch()
  return <BacktestWorkbench selectedRun={run ?? null} />
}
