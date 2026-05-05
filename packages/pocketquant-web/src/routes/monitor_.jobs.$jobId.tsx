import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useMemo } from 'react'
import { JobFiltersBar } from '../components/monitor/job-filters-bar'
import { JobRunsTable } from '../components/monitor/job-runs-table'
import { JobTimelineChart } from '../components/monitor/job-timeline-chart'
import { RunDetailDrawer } from '../components/monitor/run-detail-drawer'
import { useJobRuns } from '../hooks/use-job-runs'
import { useJobStats } from '../hooks/use-job-stats'

interface JobDetailSearch {
  run?: string
  window: '24h' | '7d' | '30d'
  status?: string
}

export const Route = createFileRoute('/monitor_/jobs/$jobId')({
  validateSearch: (s: Record<string, unknown>): JobDetailSearch => {
    const w = s.window === '7d' || s.window === '30d' ? s.window : '24h'
    return {
      run: typeof s.run === 'string' ? s.run : undefined,
      window: w,
      status: typeof s.status === 'string' ? s.status : undefined,
    }
  },
  component: JobDetailPage,
})

function windowToSince(window: '24h' | '7d' | '30d'): string {
  const days = window === '24h' ? 1 : window === '7d' ? 7 : 30
  const since = new Date(Date.now() - days * 86_400_000)
  return since.toISOString()
}

function JobDetailPage() {
  const { jobId } = Route.useParams()
  const search = Route.useSearch()
  const navigate = useNavigate()

  const since = useMemo(() => windowToSince(search.window), [search.window])

  const runsQuery = useJobRuns(jobId, {
    since,
    status: search.status,
    limit: 200,
  })
  const statsQuery = useJobStats(jobId, search.window)

  const runs = runsQuery.data ?? []
  const selectedRun = useMemo(
    () => runs.find((r) => r._id === search.run) ?? null,
    [runs, search.run],
  )

  function setSearch(patch: Partial<JobDetailSearch>) {
    void navigate({
      to: '/monitor/jobs/$jobId',
      params: { jobId },
      search: { ...search, ...patch },
    })
  }

  function selectRun(runId: string | undefined) {
    setSearch({ run: runId })
  }

  const stats = statsQuery.data
  const totalRuns = stats ? Object.values(stats.by_status).reduce((a, b) => a + (b ?? 0), 0) : 0

  return (
    <div className="monitor-page job-detail-page">
      <header className="monitor-header job-detail-header">
        <div>
          <h2 className="mono">{jobId}</h2>
          <p className="job-detail-subtitle">
            Window {search.window} · {totalRuns} runs · p50 {stats?.p50_ms ?? '—'}ms · p95{' '}
            {stats?.p95_ms ?? '—'}ms
          </p>
        </div>
        <button type="button" className="btn-sm" onClick={() => void navigate({ to: "/monitor", search: { exchange: "BINANCE", symbol: "BTCUSDT" } })}>
          ← Back to monitor
        </button>
      </header>

      <section className="monitor-section monitor-card">
        <h3>Timeline</h3>
        {runsQuery.isLoading ? (
          <div className="monitor-loading">Loading runs…</div>
        ) : runsQuery.error ? (
          <div className="monitor-error">Failed to load: {runsQuery.error.message}</div>
        ) : (
          <JobTimelineChart runs={runs} onRunClick={(id) => selectRun(id)} />
        )}
      </section>

      <section className="monitor-section monitor-card">
        <JobFiltersBar
          window={search.window}
          status={search.status}
          onWindowChange={(w) => setSearch({ window: w, run: undefined })}
          onStatusChange={(s) => setSearch({ status: s, run: undefined })}
        />
        <JobRunsTable runs={runs} selectedRunId={search.run} onSelect={selectRun} />
      </section>

      <RunDetailDrawer run={selectedRun} onClose={() => selectRun(undefined)} />
    </div>
  )
}
