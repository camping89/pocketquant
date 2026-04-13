import { useEffect, useState } from 'react'
import { createFileRoute, getRouteApi } from '@tanstack/react-router'
import { BackgroundJobsList } from '../components/monitor/background-jobs-list'
import { DataHealthTable } from '../components/monitor/data-health-table'
import { HealthBanner } from '../components/monitor/health-banner'
import { useBackgroundJobs } from '../hooks/use-background-jobs'
import { useSyncStatus } from '../hooks/use-sync-status'

export const Route = createFileRoute('/monitor')({
  component: MonitorPage,
})

const rootApi = getRouteApi('__root__')

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
  const { exchange, symbol } = rootApi.useSearch()
  const { data: syncStatuses } = useSyncStatus()
  const { data: jobs } = useBackgroundJobs()
  const [integrityTotals, setIntegrityTotals] = useState<{ misaligned: number; gaps: number } | null>(null)
  const utcTime = useUtcClock()

  const filtered = (syncStatuses ?? []).filter((s) => s.exchange === exchange && s.symbol === symbol)

  return (
    <div className="monitor-page">
      <div className="monitor-header">
        <h2>System Monitor</h2>
        <span className="utc-clock mono">{utcTime} UTC</span>
      </div>
      <HealthBanner
        syncStatuses={filtered}
        jobs={jobs ?? []}
        integrityTotals={integrityTotals}
      />
      <DataHealthTable
        exchange={exchange}
        symbol={symbol}
        onIntegrityUpdate={setIntegrityTotals}
      />
      <BackgroundJobsList />
    </div>
  )
}
