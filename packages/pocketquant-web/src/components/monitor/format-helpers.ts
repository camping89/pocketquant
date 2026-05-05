import type { IntegrityReport, SyncStatus } from '../../types/market-data'

export const INTERVAL_MS: Record<string, number> = {
  '1m': 60_000, '3m': 180_000, '5m': 300_000, '15m': 900_000,
  '30m': 1_800_000, '45m': 2_700_000, '1h': 3_600_000, '2h': 7_200_000,
  '3h': 10_800_000, '4h': 14_400_000, '1d': 86_400_000, '1w': 604_800_000,
}

function parseIso(iso: string): Date {
  return new Date(iso.endsWith('Z') ? iso : iso + 'Z')
}

export function formatAge(iso: string | null): string {
  if (!iso) return '—'
  const ms = Date.now() - parseIso(iso).getTime()
  if (Number.isNaN(ms)) return '—'
  if (ms < 60_000) return '<1m'
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m`
  if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)}h`
  return `${Math.floor(ms / 86_400_000)}d`
}

export function ageColorClass(lastBarAt: string | null, interval: string): string {
  if (!lastBarAt) return 'age-neutral'
  const ageMs = Date.now() - parseIso(lastBarAt).getTime()
  if (Number.isNaN(ageMs)) return 'age-neutral'
  const ivMs = INTERVAL_MS[interval] ?? 300_000
  if (ageMs < ivMs * 2) return 'age-fresh'
  if (ageMs < ivMs * 5) return 'age-warn'
  return 'age-stale'
}

export function statusVariant(s: SyncStatus): 'ok' | 'warn' | 'error' | 'neutral' {
  if (s.error_message) return 'error'
  // Stuck overrides "completed" green — sync ran but data isn't progressing.
  if (s.is_stuck) return 'warn'
  if (s.status === 'completed') return 'ok'
  if (s.status === 'pending') return 'warn'
  return 'neutral'
}

const UTC_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export function formatBarDate(iso: string | null): string {
  if (!iso) return '—'
  const d = parseIso(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const mon = UTC_MONTHS[d.getUTCMonth()]
  const day = d.getUTCDate()
  const hh = String(d.getUTCHours()).padStart(2, '0')
  const mm = String(d.getUTCMinutes()).padStart(2, '0')
  return `${mon} ${day} ${hh}:${mm}`
}

export function formatIntegrity(report?: IntegrityReport): string {
  if (!report) return '—'
  const parts: string[] = []
  if (report.misaligned_count > 0) parts.push(`${report.misaligned_count} misaligned`)
  if (report.missing_count > 0) parts.push(`${report.missing_count} gap${report.missing_count > 1 ? 's' : ''}`)
  return parts.length ? parts.join(' \u00b7 ') : 'OK'
}

export function integrityColorClass(report?: IntegrityReport): string {
  if (!report) return ''
  const total = report.misaligned_count + report.missing_count
  if (total === 0) return 'integrity-ok'
  if (total <= 10) return 'integrity-warn'
  return 'integrity-error'
}

export function formatDuration(ms: number | null): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  const m = Math.floor(ms / 60_000)
  const s = Math.floor((ms % 60_000) / 1000)
  return `${m}m ${s}s`
}

export function formatUtcTime(iso: string | null): string {
  if (!iso) return '—'
  const d = parseIso(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const hh = String(d.getUTCHours()).padStart(2, '0')
  const mm = String(d.getUTCMinutes()).padStart(2, '0')
  const ss = String(d.getUTCSeconds()).padStart(2, '0')
  return `${hh}:${mm}:${ss}`
}

export function formatNextRun(iso: string | null): string {
  return formatUtcTime(iso)
}

export function formatHumanizedNextRun(iso: string | null): string {
  if (!iso) return '—'
  const target = parseIso(iso)
  if (Number.isNaN(target.getTime())) return '—'
  const diffMs = target.getTime() - Date.now()
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
