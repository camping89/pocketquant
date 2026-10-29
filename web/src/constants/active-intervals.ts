// Keep in sync with backend SYNC_INTERVALS in pocketquant.engine.market_data.app_services.sync_jobs.
// sync_status rows outside this list are orphans; the Data Health table filters them out by default.
const ACTIVE_INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d', '1w'] as const

export type ActiveInterval = (typeof ACTIVE_INTERVALS)[number]

export function isActiveInterval(interval: string): boolean {
  return (ACTIVE_INTERVALS as readonly string[]).includes(interval)
}
