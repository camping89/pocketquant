import { useSyncStatus } from '../../hooks/use-sync-status'

const INTERVAL_MS: Record<string, number> = {
  '1m': 60_000, '3m': 180_000, '5m': 300_000, '15m': 900_000,
  '30m': 1_800_000, '45m': 2_700_000, '1h': 3_600_000, '2h': 7_200_000,
  '3h': 10_800_000, '4h': 14_400_000, '1d': 86_400_000, '1w': 604_800_000,
}

function ageClass(lastBarAt: string | null, interval: string): string {
  if (!lastBarAt) return 'status-stale'
  const ageMs = Date.now() - new Date(lastBarAt.endsWith('Z') ? lastBarAt : lastBarAt + 'Z').getTime()
  const ivMs = INTERVAL_MS[interval] ?? 300_000
  if (ageMs < ivMs * 2) return 'status-ok'
  if (ageMs < ivMs * 5) return 'status-warn'
  return 'status-stale'
}

function formatAge(iso: string | null): string {
  if (!iso) return '—'
  const ms = Date.now() - new Date(iso.endsWith('Z') ? iso : iso + 'Z').getTime()
  if (ms < 60_000) return '<1m'
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m`
  if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)}h`
  return `${Math.floor(ms / 86_400_000)}d`
}

interface SyncStatusTableProps {
  exchange: string
  symbol: string
}

export function SyncStatusTable({ exchange, symbol }: SyncStatusTableProps) {
  const { data, isLoading, error, dataUpdatedAt } = useSyncStatus()

  if (isLoading) return <div className="monitor-loading">Loading sync status...</div>
  if (error) return <div className="monitor-error">Failed to load sync status: {error.message}</div>
  if (!data?.length) return <div className="monitor-empty">No symbols tracked</div>

  const filtered = data.filter((s) => s.exchange === exchange && s.symbol === symbol)
  const ago = dataUpdatedAt ? formatAge(new Date(dataUpdatedAt).toISOString()) : ''

  return (
    <section className="monitor-section">
      <div className="section-header">
        <h3>Sync Status</h3>
        {ago && <span className="refresh-indicator">updated {ago} ago</span>}
      </div>
      {filtered.length === 0 ? (
        <div className="monitor-empty">No sync data for {exchange}:{symbol}</div>
      ) : (
        <div className="table-wrap">
          <table className="monitor-table">
            <thead>
              <tr>
                <th>TF</th><th>Bars</th><th>Age</th><th>Status</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => (
                <tr key={s.interval}>
                  <td className="mono">{s.interval}</td>
                  <td className="num">{s.bar_count.toLocaleString()}</td>
                  <td className="num">{formatAge(s.last_bar_at)}</td>
                  <td>
                    <span className={`status-dot ${s.error_message ? 'status-stale' : ageClass(s.last_bar_at, s.interval)}`} />
                    {s.error_message ?? s.status}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
