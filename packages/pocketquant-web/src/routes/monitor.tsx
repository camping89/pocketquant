/* eslint-disable react-refresh/only-export-components -- TanStack Router requires Route export alongside components */
import { useEffect, useState } from 'react'
import { createFileRoute } from '@tanstack/react-router'
import { BackgroundJobsList } from '../components/monitor/background-jobs-list'
import { DataHealthTable } from '../components/monitor/data-health-table'
import { HealthBanner } from '../components/monitor/health-banner'
import { useBackgroundJobs } from '../hooks/use-background-jobs'
import { useSyncStatus } from '../hooks/use-sync-status'
import { useFmt } from '../lib/use-timezone'

export const Route = createFileRoute('/monitor')({
  component: MonitorPage,
})

/** Live HH:mm:ss clock rendered in the active tz mode. */
function useClock(): string {
  const [now, setNow] = useState(() => new Date().toISOString())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date().toISOString()), 1000)
    return () => clearInterval(id)
  }, [])
  const fmt = useFmt()
  return fmt.hmsTime(now)
}

function MonitorPage() {
  const { data: syncStatuses } = useSyncStatus()
  const { data: jobs } = useBackgroundJobs()
  const [integrityTotals, setIntegrityTotals] = useState<{ misaligned: number; gaps: number } | null>(null)
  const clock = useClock()

  return (
    <div className="monitor-page">
      <div className="monitor-header">
        <h2>System Monitor</h2>
        <span className="utc-clock mono">{clock}</span>
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
