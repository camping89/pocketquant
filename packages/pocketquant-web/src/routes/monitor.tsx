import { createFileRoute } from '@tanstack/react-router'
import { SyncStatusTable } from '../components/monitor/sync-status-table'
import { IntegrityPanel } from '../components/monitor/integrity-panel'
import { BackgroundJobsList } from '../components/monitor/background-jobs-list'

export const Route = createFileRoute('/monitor')({
  component: MonitorPage,
})

function MonitorPage() {
  return (
    <div className="monitor-page">
      <h2>System Monitor</h2>
      <SyncStatusTable />
      <IntegrityPanel />
      <BackgroundJobsList />
    </div>
  )
}
