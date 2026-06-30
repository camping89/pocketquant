import { useBacktestRun } from '../../hooks/use-backtest-run'
import type { BacktestRunResult } from '../../api/backtest-api'
import { EquityOverlay, SERIES_COLORS } from './equity-overlay'
import { MetricsDiffTable } from './metrics-diff-table'

const sectionTitle = {
  fontSize: 12,
  fontWeight: 600,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase' as const,
  letterSpacing: 0.4,
  margin: '12px 0 6px',
}

/** Compare 2–3 runs (validation Q2: cross-scope allowed). Fixed 3 hook slots keep
 *  the Rules of Hooks intact; absent run ids resolve to disabled queries. */
export function RunCompareView({ runIds }: { runIds: string[] }) {
  const q0 = useBacktestRun(runIds[0] ?? null)
  const q1 = useBacktestRun(runIds[1] ?? null)
  const q2 = useBacktestRun(runIds[2] ?? null)

  const runs = [q0.data, q1.data, q2.data]
    .slice(0, runIds.length)
    .filter((r): r is BacktestRunResult => r != null && r.status === 'finished')

  const loading = [q0, q1, q2].slice(0, runIds.length).some((q) => q.isLoading)

  if (loading && runs.length < runIds.length) {
    return <div className="empty-state" style={{ padding: 24 }}>Loading runs…</div>
  }
  if (runs.length < 2) {
    return <div className="empty-state" style={{ padding: 24 }}>Need at least 2 finished runs to compare.</div>
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 12 }}>
        {runs.map((r, i) => (
          <span key={r.id ?? i} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: SERIES_COLORS[i % SERIES_COLORS.length] }} />
            {r.strategy_code} · {String(r.config_snapshot?.symbol ?? '')}
          </span>
        ))}
      </div>
      <div style={sectionTitle}>Equity (normalized % return)</div>
      <EquityOverlay runs={runs} />
      <div style={sectionTitle}>Metrics</div>
      <MetricsDiffTable runs={runs} />
    </div>
  )
}
