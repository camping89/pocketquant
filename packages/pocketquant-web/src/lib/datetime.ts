// Pure datetime formatting library — tz-mode aware.
// Inputs: ISO strings (DB sends naive UTC without `Z` suffix — we append `Z` so dayjs parses as UTC).
// Outputs: formatted strings with tz suffix (`UTC` or `GMT+7`).
// NO React imports here — React layer lives in timezone-context.tsx.

import dayjs, { type Dayjs } from 'dayjs'
import utc from 'dayjs/plugin/utc'

dayjs.extend(utc)

export type TimezoneMode = 'utc' | 'local'

const PLACEHOLDER = '—'

/** Parse an ISO string treating naive (no Z/offset) strings as UTC. */
export function parseIso(iso: string | null | undefined): Dayjs | null {
  if (!iso) return null
  // If string has no `Z` and no trailing numeric offset (e.g. +07:00 / -05:30), treat as UTC.
  const hasOffset = /Z$|[+-]\d{2}:?\d{2}$/.test(iso)
  const normalized = hasOffset ? iso : iso + 'Z'
  const d = dayjs.utc(normalized)
  return d.isValid() ? d : null
}

/** Returns suffix label for the current tz mode (e.g. `UTC`, `GMT+7`, `GMT-5:30`). */
export function tzSuffix(mode: TimezoneMode): string {
  if (mode === 'utc') return 'UTC'
  // getTimezoneOffset returns minutes with INVERTED sign (positive for west of UTC).
  const offsetMin = -new Date().getTimezoneOffset()
  const sign = offsetMin >= 0 ? '+' : '-'
  const abs = Math.abs(offsetMin)
  const h = Math.floor(abs / 60)
  const m = abs % 60
  return m === 0 ? `GMT${sign}${h}` : `GMT${sign}${h}:${String(m).padStart(2, '0')}`
}

/** Core formatter — null-safe, returns `'—'` for null/invalid. */
export function formatDateTime(
  iso: string | null | undefined,
  mode: TimezoneMode,
  fmt: string,
): string {
  const parsed = parseIso(iso)
  if (!parsed) return PLACEHOLDER
  const inMode = mode === 'utc' ? parsed.utc() : parsed.local()
  return `${inMode.format(fmt)} ${tzSuffix(mode)}`
}

/** `MMM D HH:mm` — used for bar dates / next run rows. */
export function formatBarDate(iso: string | null | undefined, mode: TimezoneMode): string {
  return formatDateTime(iso, mode, 'MMM D HH:mm')
}

/** `HH:mm:ss` — clock-style time. */
export function formatHmsTime(iso: string | null | undefined, mode: TimezoneMode): string {
  return formatDateTime(iso, mode, 'HH:mm:ss')
}

/** Alias of formatHmsTime — kept distinct for callsite clarity. */
export function formatNextRun(iso: string | null | undefined, mode: TimezoneMode): string {
  return formatHmsTime(iso, mode)
}

/** `YYYY-MM-DD HH:mm` — full timestamp with date. */
export function formatFullDateTime(iso: string | null | undefined, mode: TimezoneMode): string {
  return formatDateTime(iso, mode, 'YYYY-MM-DD HH:mm')
}

// ─── tz-independent helpers (elapsed time / humanized — same regardless of mode) ───

const INTERVAL_MS: Record<string, number> = {
  '1m': 60_000, '3m': 180_000, '5m': 300_000, '15m': 900_000,
  '30m': 1_800_000, '45m': 2_700_000, '1h': 3_600_000, '2h': 7_200_000,
  '3h': 10_800_000, '4h': 14_400_000, '1d': 86_400_000, '1w': 604_800_000,
}

export { INTERVAL_MS }

/** Elapsed since `iso`. Returns `<1m`, `5m`, `2h`, `3d`, etc. */
export function formatAge(iso: string | null): string {
  const parsed = parseIso(iso)
  if (!parsed) return PLACEHOLDER
  const ms = Date.now() - parsed.valueOf()
  if (Number.isNaN(ms)) return PLACEHOLDER
  if (ms < 60_000) return '<1m'
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m`
  if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)}h`
  return `${Math.floor(ms / 86_400_000)}d`
}

export function ageColorClass(lastBarAt: string | null, interval: string): string {
  const parsed = parseIso(lastBarAt)
  if (!parsed) return 'age-neutral'
  const ageMs = Date.now() - parsed.valueOf()
  if (Number.isNaN(ageMs)) return 'age-neutral'
  const ivMs = INTERVAL_MS[interval] ?? 300_000
  if (ageMs < ivMs * 2) return 'age-fresh'
  if (ageMs < ivMs * 5) return 'age-warn'
  return 'age-stale'
}

/** Humanized "in 5m", "2h ago", etc. Tz-independent — uses elapsed only. */
export function formatHumanizedNextRun(iso: string | null): string {
  const parsed = parseIso(iso)
  if (!parsed) return PLACEHOLDER
  const diffMs = parsed.valueOf() - Date.now()
  const past = diffMs < 0
  const abs = Math.abs(diffMs)
  let text: string
  if (abs < 1_000) text = 'now'
  else if (abs < 60_000) text = `${Math.round(abs / 1_000)}s`
  else if (abs < 3_600_000) {
    const m = Math.floor(abs / 60_000)
    const s = Math.floor((abs % 60_000) / 1_000)
    text = s > 0 && m < 5 ? `${m}m ${s}s` : `${m}m`
  } else if (abs < 86_400_000) {
    const h = Math.floor(abs / 3_600_000)
    const m = Math.floor((abs % 3_600_000) / 60_000)
    text = m > 0 ? `${h}h ${m}m` : `${h}h`
  } else {
    const d = Math.floor(abs / 86_400_000)
    const h = Math.floor((abs % 86_400_000) / 3_600_000)
    text = h > 0 ? `${d}d ${h}h` : `${d}d`
  }
  if (text === 'now') return 'now'
  return past ? `${text} ago` : `in ${text}`
}

export function formatDuration(ms: number | null): string {
  if (ms == null) return PLACEHOLDER
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  const m = Math.floor(ms / 60_000)
  const s = Math.floor((ms % 60_000) / 1000)
  return `${m}m ${s}s`
}

/** Unix-seconds chart timestamp → formatted string for lightweight-charts. */
export function makeChartTimeFormatter(mode: TimezoneMode): (t: number) => string {
  return (t: number) => {
    const d = dayjs.unix(t).utc()
    const inMode = mode === 'utc' ? d : d.local()
    return `${inMode.format('YYYY-MM-DD HH:mm')} ${tzSuffix(mode)}`
  }
}
