/** Intervals actively synced by background jobs.
 *  Rows in sync_status with intervals outside this list are orphans (filtered
 *  in the Data Health table by default). Keep in sync with backend
 *  `SYNC_INTERVALS` in `pocketquant.engine.market_data.app_services.sync_jobs`. */
const ACTIVE_INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d', '1w'] as const

export type ActiveInterval = (typeof ACTIVE_INTERVALS)[number]

export function isActiveInterval(interval: string): boolean {
  return (ACTIVE_INTERVALS as readonly string[]).includes(interval)
}
