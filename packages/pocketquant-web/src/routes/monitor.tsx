/* eslint-disable react-refresh/only-export-components -- TanStack Router requires Route export alongside components */
import { useEffect, useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { BackgroundJobsList } from '../components/monitor/background-jobs-list'
import { DataHealthTable } from '../components/monitor/data-health-table'
import { HealthBanner } from '../components/monitor/health-banner'
import { useBackgroundJobs } from '../hooks/use-background-jobs'
import { useSyncStatus } from '../hooks/use-sync-status'

export const Route = createFileRoute('/monitor')({
  component: MonitorPage,
})

function useUtcClock(): string {
  const fmt = (d: Date) => {
    const hh = String(d.getUTCHours()).padStart(2, '0')
    const mm = String(d.getUTCMinutes()).padStart(2, '0')
    const ss = String(d.getUTCSeconds()).padStart(2, '0')
    return `${hh}:${mm}:${ss}`
  }
  const [time, setTime] = useState(() => fmt(new Date()))
  useEffect(() => {
    const id = setInterval(() => setTime(fmt(new Date())), 1000)
    return () => clearInterval(id)
  }, [])
  return time
}

function MonitorPage() {
  const { data: syncStatuses } = useSyncStatus()
  const { data: jobs } = useBackgroundJobs()
  const [integrityTotals, setIntegrityTotals] = useState<{ misaligned: number; gaps: number } | null>(null)
  const utcTime = useUtcClock()

  return (
    <div className="monitor-page">
      <div className="monitor-header">
        <h2>System Monitor</h2>
        <span className="utc-clock mono">{utcTime} UTC</span>
      </div>
      <HealthBanner
        syncStatuses={syncStatuses ?? []}
        jobs={jobs ?? []}
        integrityTotals={integrityTotals}
      />
      <DataHealthTable onIntegrityUpdate={setIntegrityTotals} />
      <BackgroundJobsList />
    </div>
  )
}
