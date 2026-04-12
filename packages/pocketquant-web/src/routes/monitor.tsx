import { createFileRoute, getRouteApi } from '@tanstack/react-router'
import { SyncStatusTable } from '../components/monitor/sync-status-table'
import { IntegrityPanel } from '../components/monitor/integrity-panel'
import { BackgroundJobsList } from '../components/monitor/background-jobs-list'

export const Route = createFileRoute('/monitor')({
  component: MonitorPage,
})

const rootApi = getRouteApi('__root__')

function MonitorPage() {
  const { exchange, symbol } = rootApi.useSearch()

  return (
    <div className="monitor-page">
      <h2>System Monitor</h2>
      <SyncStatusTable exchange={exchange} symbol={symbol} />
      <IntegrityPanel exchange={exchange} symbol={symbol} />
      <BackgroundJobsList />
    </div>
  )
}
