import { Fragment, useState } from 'react'
import { useBackgroundJobs } from '../../hooks/use-background-jobs'
import type { JobInfo } from '../../types/market-data'
import { formatDuration, formatNextRun, formatUtcTime } from './format-helpers'
import { SparklineStrip } from './sparkline-strip'
import { StatusPill } from './status-pill'

function jobStatus(job: JobInfo): { variant: 'ok' | 'warn' | 'error' | 'neutral'; label: string } {
  const last = job.last_run?.status
  if (last === 'failed' || last === 'missed' || last === 'skipped_max_instances')
    return { variant: 'error', label: last === 'failed' ? 'failed' : last.replace('_', ' ') }
  if (!job.next_run) return { variant: 'neutral', label: 'never' }
  const overdue = Date.now() - new Date(job.next_run.endsWith('Z') ? job.next_run : job.next_run + 'Z').getTime()
  if (overdue > 60_000) return { variant: 'warn', label: 'overdue' }
  if (!job.last_run) return { variant: 'neutral', label: 'pending' }
  return { variant: 'ok', label: 'OK' }
}

export function BackgroundJobsList() {
  const { data, isLoading, error } = useBackgroundJobs()
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  if (isLoading) return <div className="monitor-loading">Loading jobs...</div>
  if (error) return <div className="monitor-error">Failed to load jobs: {error.message}</div>
  if (!data?.length) return <div className="monitor-empty">No scheduled jobs</div>

  function toggle(id: string) {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  return (
    <section className="monitor-section monitor-card">
      <div className="section-header">
        <h3>Background Jobs</h3>
        <span className="section-subtitle">Click any row to view last 20 runs · drilldown for full history</span>
      </div>
      <div className="table-wrap">
        <table className="monitor-table">
          <thead>
            <tr>
              <th>Job</th>
              <th>Trigger</th>
              <th>Last Run</th>
              <th>Duration</th>
              <th>Next Run</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {data.map((job) => {
              const s = jobStatus(job)
              const isOpen = !!expanded[job.id]
              return (
                <Fragment key={job.id}>
                  <tr
                    className={isOpen ? 'row-expanded' : ''}
                    style={{ cursor: 'pointer' }}
                    onClick={() => toggle(job.id)}
                  >
                    <td className="mono">
                      {isOpen ? '▼' : '▶'} {job.id}
                    </td>
                    <td>{job.trigger}</td>
                    <td className="mono">{formatUtcTime(job.last_run?.started_at ?? null)}</td>
                    <td className="mono">{formatDuration(job.last_run?.duration_ms ?? null)}</td>
                    <td className="mono">{formatNextRun(job.next_run)}</td>
                    <td>
                      <StatusPill variant={s.variant} label={s.label} />
                    </td>
                  </tr>
                  {isOpen && (
                    <tr>
                      <td colSpan={6} className="sparkline-cell">
                        <SparklineStrip jobId={job.id} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
