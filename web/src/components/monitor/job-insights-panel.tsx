import { useJobRuns } from '../../hooks/use-job-runs'
import { useJobStats } from '../../hooks/use-job-stats'
import type { JobRun, JobRunStatus } from '../../types/job-history'
import { SparklineStrip } from './sparkline-strip'
import { STATUS_LABEL, statusColor } from './job-status-palette'

interface JobInsightsPanelProps {
  jobId: string
}

function fmtMs(ms: number | null): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

function findLastError(runs: JobRun[] | undefined): JobRun | null {
  if (!runs?.length) return null
  return runs.find((r) => r.status === 'failed' || r.status === 'error' || r.status === 'stuck') ?? null
}

export function JobInsightsPanel({ jobId }: JobInsightsPanelProps) {
  const { data: stats, isLoading: statsLoading } = useJobStats(jobId, '24h')
  const { data: runs } = useJobRuns(jobId, { limit: 30 })

  const total = stats ? Object.values(stats.by_status).reduce((a, b) => a + (b ?? 0), 0) : 0
  const okCount = stats?.by_status.completed ?? 0
  const successRate = total > 0 ? Math.round((okCount / total) * 100) : null
  const failedCount =
    (stats?.by_status.failed ?? 0) + (stats?.by_status.error ?? 0) + (stats?.by_status.stuck ?? 0)
  const missedCount = (stats?.by_status.missed ?? 0) + (stats?.by_status.skipped_max_instances ?? 0)

  const lastError = findLastError(runs)

  return (
    <div className="job-insights">
      <div className="insights-row">
        <div className="insight-stat">
          <div className="insight-stat-label">Success (24h)</div>
          <div className="insight-stat-value">
            {statsLoading ? '…' : successRate == null ? '—' : `${successRate}%`}
            {total > 0 && <span className="insight-stat-sub"> ({okCount}/{total})</span>}
          </div>
        </div>
        <div className="insight-stat">
          <div className="insight-stat-label">p50 / p95</div>
          <div className="insight-stat-value">
            {fmtMs(stats?.p50_ms ?? null)} <span className="insight-stat-sep">/</span> {fmtMs(stats?.p95_ms ?? null)}
          </div>
        </div>
        <div className="insight-stat">
          <div className="insight-stat-label">Failed / Missed</div>
          <div className="insight-stat-value">
            <span className="insight-bad">{failedCount}</span>
            <span className="insight-stat-sep"> / </span>
            <span className="insight-warn">{missedCount}</span>
          </div>
        </div>
        <div className="insight-stat insight-stat-breakdown">
          <div className="insight-stat-label">Status (24h)</div>
          <div className="insight-status-pills">
            {stats &&
              (Object.entries(stats.by_status) as Array<[JobRunStatus, number | undefined]>)
                .filter(([, n]) => (n ?? 0) > 0)
                .map(([s, n]) => (
                  <span
                    key={s}
                    className="insight-status-pill"
                    style={{ backgroundColor: statusColor(s) }}
                    title={`${STATUS_LABEL[s] ?? s}: ${n}`}
                  >
                    {STATUS_LABEL[s] ?? s} {n}
                  </span>
                ))}
            {!stats && <span className="insight-stat-sub">—</span>}
          </div>
        </div>
      </div>

      <div className="insights-strip">
        <span className="insights-strip-label">Last 20 runs</span>
        <SparklineStrip jobId={jobId} cellCount={20} />
      </div>

      {lastError && (
        <div className="insight-error" title={lastError.error ?? ''}>
          <span className="insight-error-tag">Last {STATUS_LABEL[lastError.status] ?? lastError.status}</span>
          <span className="insight-error-msg">{lastError.error ?? '(no message)'}</span>
        </div>
      )}
    </div>
  )
}
