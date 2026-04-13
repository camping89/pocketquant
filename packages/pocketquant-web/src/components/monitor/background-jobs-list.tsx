import { useBackgroundJobs } from '../../hooks/use-background-jobs'
import type { JobInfo } from '../../types/market-data'
import { formatDuration, formatNextRun, formatUtcTime } from './format-helpers'
import { StatusPill } from './status-pill'

function jobStatus(job: JobInfo): { variant: 'ok' | 'warn' | 'error' | 'neutral'; label: string } {
  if (job.last_run?.status === 'failed') return { variant: 'error', label: 'failed' }
  if (!job.next_run) return { variant: 'neutral', label: 'never' }
  const overdue = Date.now() - new Date(job.next_run.endsWith('Z') ? job.next_run : job.next_run + 'Z').getTime()
  if (overdue > 60_000) return { variant: 'warn', label: 'overdue' }
  if (!job.last_run) return { variant: 'neutral', label: 'never' }
  return { variant: 'ok', label: 'OK' }
}

export function BackgroundJobsList() {
  const { data, isLoading, error } = useBackgroundJobs()

  if (isLoading) return <div className="monitor-loading">Loading jobs...</div>
  if (error) return <div className="monitor-error">Failed to load jobs: {error.message}</div>
  if (!data?.length) return <div className="monitor-empty">No scheduled jobs</div>

  return (
    <section className="monitor-section monitor-card">
      <div className="section-header">
        <h3>Background Jobs</h3>
        <span className="section-subtitle">System-wide — not filtered by symbol</span>
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
              return (
                <tr key={job.id}>
                  <td className="mono">{job.id}</td>
                  <td>{job.trigger}</td>
                  <td className="mono">{formatUtcTime(job.last_run?.started_at ?? null)}</td>
                  <td className="mono">{formatDuration(job.last_run?.duration_ms ?? null)}</td>
                  <td className="mono">{formatNextRun(job.next_run)}</td>
                  <td>
                    <StatusPill variant={s.variant} label={s.label} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
