import { useMemo, type CSSProperties } from 'react'
import type { EquityPoint } from '../../api/backtest-api'
import { fmtDuration } from '../strategy/backtest-panel/metric-cards'
import { topDrawdowns } from './stats-utils'

function fmtDate(iso: string): string {
  // Compact YYYY-MM-DD HH:mm; the curve carries naive-UTC ISO strings.
  return iso.replace('T', ' ').slice(0, 16)
}

/** Top-5 worst drawdown periods: depth, peak→trough window, recovery, duration. */
export function DrawdownTable({ equityCurve }: { equityCurve: EquityPoint[] }) {
  const periods = useMemo(() => topDrawdowns(equityCurve, 5), [equityCurve])

  if (periods.length === 0) {
    return <div className="empty-state" style={{ padding: 16 }}>No drawdown periods — equity never dipped below its peak.</div>
  }

  const th: CSSProperties = {
    textAlign: 'left',
    padding: '6px 10px',
    color: 'var(--text-secondary)',
    fontWeight: 600,
    borderBottom: '1px solid var(--border-color)',
  }
  const td: CSSProperties = { padding: '6px 10px', borderBottom: '1px solid var(--border-color)' }

  return (
    <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse', color: 'var(--text-primary)' }}>
      <thead>
        <tr>
          <th style={{ ...th, textAlign: 'right' }}>Depth</th>
          <th style={th}>Start</th>
          <th style={th}>Trough</th>
          <th style={th}>Recovery</th>
          <th style={{ ...th, textAlign: 'right' }}>Duration</th>
        </tr>
      </thead>
      <tbody>
        {periods.map((p, i) => (
          <tr key={i}>
            <td style={{ ...td, textAlign: 'right', color: 'var(--down-color)', fontWeight: 600 }}>
              {(p.depth * 100).toFixed(2)}%
            </td>
            <td style={td}>{fmtDate(p.startTime)}</td>
            <td style={td}>{fmtDate(p.troughTime)}</td>
            <td style={td}>{p.recoveryTime ? fmtDate(p.recoveryTime) : <span style={{ color: 'var(--text-secondary)' }}>under water</span>}</td>
            <td style={{ ...td, textAlign: 'right' }}>{fmtDuration(p.durationSeconds)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
