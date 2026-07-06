import type { TradeRow, TradeSortKey, TradeSortDir, TradeFilterKey } from '../../../api/backtest-api'
import { formatDateTime, type TimezoneMode } from '../../../lib/datetime'

export { formatPrice as fmtPrice } from '../../../lib/number-format'

// Filtering + sorting run server-side now; these re-exports keep call-sites on
// the API's canonical union names.
export type FilterKey = TradeFilterKey
export type SortKey = TradeSortKey
export type SortDir = TradeSortDir

export function fmtDurationSeconds(sec: number): string {
  if (!isFinite(sec) || sec < 0) return '—'
  if (sec < 60) return `${Math.round(sec)}s`
  if (sec < 3600) return `${Math.round(sec / 60)}m`
  if (sec < 86400) {
    const h = Math.floor(sec / 3600)
    const m = Math.floor((sec % 3600) / 60)
    return `${h}h ${m}m`
  }
  const d = Math.floor(sec / 86400)
  const h = Math.floor((sec % 86400) / 3600)
  return `${d}d ${h}h`
}

export function fmtDuration(t: TradeRow): string {
  if (!t.exit_time) return '—'
  return fmtDurationSeconds(t.duration_seconds)
}

export function fmtDateTime(s: string, mode: TimezoneMode): string {
  return formatDateTime(s, mode, 'YYYY-MM-DD HH:mm')
}
