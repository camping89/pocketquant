import type { IntegrityReport, RepairResult, SyncStatus } from '../../types/market-data'
import { useFmt } from '../../lib/use-timezone'

interface DataHealthDetailProps {
  syncStatus: SyncStatus
  report?: IntegrityReport
  repair?: RepairResult
}

export function DataHealthDetail({ syncStatus, report, repair }: DataHealthDetailProps) {
  const fmt = useFmt()
  return (
    <div className="detail-panel">
      <dl>
        <dt>Last Sync</dt>
        <dd>{fmt.barDate(syncStatus.last_sync_at)}</dd>

        <dt>Total Bars</dt>
        <dd>{syncStatus.bar_count?.toLocaleString() ?? '—'}</dd>

        {report && (
          <>
            <dt>Misaligned</dt>
            <dd>
              {report.misaligned_count === 0
                ? 'None'
                : `${report.misaligned_count} bars — ${report.misaligned_ids.slice(0, 5).join(', ')}${report.misaligned_ids.length > 5 ? '...' : ''}`}
            </dd>

            <dt>Gaps</dt>
            <dd>
              {report.missing_count === 0
                ? 'None'
                : report.gap_ranges.map(([from, to], i) => (
                    <div key={i} className="mono">
                      {fmt.barDate(from)} → {fmt.barDate(to)}
                    </div>
                  ))}
            </dd>
          </>
        )}

        {repair && (
          <>
            <dt>Repair Result</dt>
            <dd className="repair-result">
              Deleted {repair.deleted}, resynced {repair.gaps_resynced} gaps
            </dd>
          </>
        )}

        {syncStatus.error_message && (
          <>
            <dt>Error</dt>
            <dd className="text-error">{syncStatus.error_message}</dd>
          </>
        )}
      </dl>
    </div>
  )
}
