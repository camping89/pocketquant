import { useBackgroundJobs } from '../../hooks/use-background-jobs'

function formatNextRun(iso: string | null): string {
  if (!iso) return '—'
  const dt = new Date(iso.endsWith('Z') ? iso : iso + 'Z')
  return dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function BackgroundJobsList() {
  const { data, isLoading, error } = useBackgroundJobs()

  if (isLoading) return <div className="monitor-loading">Loading jobs...</div>
  if (error) return <div className="monitor-error">Failed to load jobs: {error.message}</div>
  if (!data?.length) return <div className="monitor-empty">No scheduled jobs</div>

  return (
    <section className="monitor-section">
      <div className="section-header">
        <h3>Background Jobs</h3>
        <span className="section-subtitle">System-wide — not filtered by symbol</span>
      </div>
      <div className="table-wrap">
        <table className="monitor-table">
          <thead>
            <tr><th>Job</th><th>Trigger</th><th>Next Run</th></tr>
          </thead>
          <tbody>
            {data.map((job) => (
              <tr key={job.id}>
                <td className="mono">{job.id}</td>
                <td>{job.trigger}</td>
                <td>{formatNextRun(job.next_run)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
