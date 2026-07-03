/* eslint-disable react-refresh/only-export-components -- TanStack Router requires Route export alongside components */
import { createFileRoute } from '@tanstack/react-router'
import { BacktestWorkbench } from '../components/backtest/backtest-workbench'

/** Run + tab live in the path (`/backtest/<runId>/<tab>`) so every view is
 *  bookmarkable and reload/back/forward safe; both segments are optional, so
 *  `/backtest` (no run) and `/backtest/<runId>` (default tab) also match. */
export const Route = createFileRoute('/backtest/{-$runId}/{-$tab}')({
  errorComponent: () => (
    <div className="empty-state empty-state--error" style={{ padding: 24 }}>
      <div>✗ Failed to render this view</div>
      <div className="empty-state__sub">Try selecting another run or reloading.</div>
    </div>
  ),
  component: BacktestPage,
})

function BacktestPage() {
  const { runId, tab } = Route.useParams()
  return <BacktestWorkbench selectedRun={runId ?? null} activeTab={tab} />
}
