import type { IntegrityReport, RepairResult, SyncStatus } from '../../types/market-data'
import { DataHealthDetail } from './data-health-detail'
import {
  ageColorClass,
  formatAge,
  formatBarDate,
  formatIntegrity,
  integrityColorClass,
  statusVariant,
} from './format-helpers'
import { StatusPill } from './status-pill'

interface DataHealthRowProps {
  syncStatus: SyncStatus
  report?: IntegrityReport
  repair?: RepairResult
  expanded: boolean
  checking: boolean
  repairing: boolean
  onToggle: () => void
  onCheck: () => void
  onRepair: () => void
}

export function DataHealthRow({
  syncStatus: s,
  report,
  repair,
  expanded,
  checking,
  repairing,
  onToggle,
  onCheck,
  onRepair,
}: DataHealthRowProps) {
  const hasIssues = report && (report.misaligned_count > 0 || report.missing_count > 0)
  const rowClass = [
    expanded ? 'row-expanded' : '',
    report && hasIssues && (report.misaligned_count + report.missing_count) > 10 ? 'row-error' : '',
    report && hasIssues && (report.misaligned_count + report.missing_count) <= 10 ? 'row-warn' : '',
  ]
    .filter(Boolean)
    .join(' ')

  const variant = statusVariant(s)
  const statusLabel = s.error_message ? 'error' : s.status === 'completed' ? 'synced' : s.status

  return (
    <>
      <tr className={rowClass} onClick={onToggle} style={{ cursor: 'pointer' }}>
        <td className="mono">
          {expanded ? '\u25BC' : '\u25B6'} {s.interval}
        </td>
        <td className="num">{s.bar_count?.toLocaleString() ?? '—'}</td>
        <td className="num">{formatBarDate(s.last_bar_at)}</td>
        <td className={`num ${ageColorClass(s.last_bar_at, s.interval)}`}>{formatAge(s.last_bar_at)}</td>
        <td className={integrityColorClass(report)}>{formatIntegrity(report)}</td>
        <td>
          <StatusPill variant={variant} label={statusLabel} />
        </td>
        <td className="actions" onClick={(e) => e.stopPropagation()}>
          <button className="btn" disabled={checking} onClick={onCheck}>
            {checking ? '...' : 'Check'}
          </button>
          {hasIssues && !repair && (
            <button className="btn btn-warn" disabled={repairing} onClick={onRepair}>
              {repairing ? '...' : 'Repair'}
            </button>
          )}
          {repair && (
            <span className="repair-result">
              Deleted {repair.deleted}, resynced {repair.gaps_resynced} gaps
            </span>
          )}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={7} style={{ padding: 0 }}>
            <DataHealthDetail syncStatus={s} report={report} repair={repair} />
          </td>
        </tr>
      )}
    </>
  )
}
