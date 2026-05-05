import type { JobRun } from '../../types/job-history'
import { statusColor, statusLabel } from './job-status-palette'

interface JobRunsTableProps {
  runs: JobRun[]
  selectedRunId?: string
  onSelect: (runId: string) => void
}

function fmt(iso: string | null): string {
  if (!iso) return '—'
  return iso.replace('T', ' ').replace(/\.\d+Z?$/, '').replace('Z', '')
}

export function JobRunsTable({ runs, selectedRunId, onSelect }: JobRunsTableProps) {
  if (!runs.length) return <div className="monitor-empty">No runs in window</div>
  return (
    <div className="table-wrap">
      <table className="monitor-table job-runs-table">
        <thead>
          <tr>
            <th>Started</th>
            <th>Duration</th>
            <th>Status</th>
            <th className="num">Inserted</th>
            <th className="num">Fetched</th>
            <th className="num">Symbols</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => {
            const isSelected = r._id === selectedRunId
            const failedCount = r.details.filter((d) => d.status !== 'completed').length
            return (
              <tr
                key={r._id}
                className={isSelected ? 'row-selected' : ''}
                style={{ cursor: 'pointer' }}
                onClick={() => onSelect(r._id)}
              >
                <td className="mono">{fmt(r.started_at)}</td>
                <td className="mono num">{r.duration_ms ?? '—'} ms</td>
                <td>
                  <span
                    className="status-pill"
                    style={{ backgroundColor: statusColor(r.status), color: '#0b1220' }}
                  >
                    {statusLabel(r.status)}
                  </span>
                </td>
                <td className="num">{r.total_inserted ?? '—'}</td>
                <td className="num">{r.total_fetched ?? '—'}</td>
                <td className="num">
                  {r.details.length}
                  {failedCount > 0 ? ` (${failedCount} failed)` : ''}
                </td>
                <td className="run-error" title={r.error ?? ''}>
                  {r.error ? r.error.slice(0, 80) : ''}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
