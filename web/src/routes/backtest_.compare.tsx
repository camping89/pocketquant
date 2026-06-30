/* eslint-disable react-refresh/only-export-components -- TanStack Router requires Route export alongside components */
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { RunCompareView } from '../components/backtest/run-compare-view'

interface CompareSearch {
  runs: string[]
}

/** Parse ``?runs=a,b,c`` into ≤3 ids; the comma-joined form keeps the URL short
 *  and shareable. RunCompareView is filled in Phase 4. */
function parseRuns(raw: unknown): string[] {
  const csv = typeof raw === 'string' ? raw : Array.isArray(raw) ? raw.join(',') : ''
  return csv
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 3)
}

export const Route = createFileRoute('/backtest_/compare')({
  validateSearch: (s: Record<string, unknown>): CompareSearch => ({ runs: parseRuns(s.runs) }),
  component: BacktestComparePage,
})

function BacktestComparePage() {
  const { runs } = Route.useSearch()
  const navigate = useNavigate()

  return (
    <div style={{ maxWidth: 1080, margin: '0 auto', padding: '24px 16px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <button type="button" className="btn-sm" onClick={() => void navigate({ to: '/backtest' })}>
          ← Backtest
        </button>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>Compare</span>
      </div>

      {runs.length === 0 ? (
        <div className="empty-state" style={{ padding: 24 }}>
          <div>Select 2–3 runs from the history rail to compare.</div>
        </div>
      ) : (
        <RunCompareView runIds={runs} />
      )}
    </div>
  )
}
