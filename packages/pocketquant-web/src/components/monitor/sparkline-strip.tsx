import { useNavigate, useSearch } from '@tanstack/react-router'
import { useJobRuns } from '../../hooks/use-job-runs'
import type { JobRun } from '../../types/job-history'
import { statusColor, statusLabel } from './job-status-palette'

interface SparklineStripProps {
  jobId: string
  cellCount?: number
  compact?: boolean
}

function fmtTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso.endsWith('Z') ? iso : `${iso}Z`)
  const hh = String(d.getUTCHours()).padStart(2, '0')
  const mm = String(d.getUTCMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
}

export function SparklineStrip({ jobId, cellCount = 20, compact = false }: SparklineStripProps) {
  const navigate = useNavigate()
  const rootSearch = useSearch({ from: '__root__' })
  const { data, isLoading, error } = useJobRuns(jobId, { limit: cellCount })

  const wrapCls = compact ? 'sparkline-wrap sparkline-compact' : 'sparkline-wrap'
  const stripCls = compact ? 'sparkline-strip sparkline-strip-compact' : 'sparkline-strip'

  if (isLoading) return <div className={`${stripCls} sparkline-loading`}>{compact ? '…' : 'Loading…'}</div>
  if (error)
    return (
      <div className={`${stripCls} sparkline-error`} title={error.message}>
        {compact ? '!' : `Failed: ${error.message}`}
      </div>
    )

  const runs: JobRun[] = (data ?? []).slice(0, cellCount).reverse()
  const padding = cellCount - runs.length

  return (
    <div className={wrapCls}>
      <div className={stripCls} role="list" aria-label={`Last ${cellCount} runs of ${jobId}`}>
        {Array.from({ length: padding }, (_, i) => (
          <span key={`pad-${i}`} className="spark-cell spark-empty" aria-hidden />
        ))}
        {runs.map((r) => {
          const cls = r.status === 'running' ? 'spark-cell spark-pulse' : 'spark-cell'
          const tip = `${fmtTime(r.started_at)} · ${statusLabel(r.status)} · ${r.duration_ms ?? '?'}ms`
          return (
            <button
              key={r._id}
              type="button"
              className={cls}
              role="listitem"
              aria-label={tip}
              title={tip}
              style={{ backgroundColor: statusColor(r.status) }}
              onClick={(e) => {
                e.stopPropagation()
                navigate({
                  to: '/monitor/jobs/$jobId',
                  params: { jobId },
                  search: { ...rootSearch, run: r._id, window: '24h' },
                })
              }}
            />
          )
        })}
      </div>
      {!compact && (
        <button
          type="button"
          className="sparkline-link"
          onClick={(e) => {
            e.stopPropagation()
            navigate({
              to: '/monitor/jobs/$jobId',
              params: { jobId },
              search: { ...rootSearch, window: '24h' },
            })
          }}
        >
          View details →
        </button>
      )}
    </div>
  )
}
