// Monitor-specific formatters that depend on monitor types.
// Tz-aware formatters moved to `src/lib/datetime.ts` — use `useFmt()` from `src/lib/use-timezone.ts`.
// Tz-independent helpers re-exported here for backward-compatible imports.

import type { IntegrityReport, SyncStatus } from '../../types/market-data'

export {
  INTERVAL_MS,
  parseIso,
  formatAge,
  ageColorClass,
  formatDuration,
  formatHumanizedNextRun,
} from '../../lib/datetime'

export function statusVariant(s: SyncStatus): 'ok' | 'warn' | 'error' | 'neutral' {
  if (s.error_message) return 'error'
  // Stuck overrides "completed" green — sync ran but data isn't progressing.
  if (s.is_stuck) return 'warn'
  if (s.status === 'completed') return 'ok'
  if (s.status === 'pending') return 'warn'
  return 'neutral'
}

export function formatIntegrity(report?: IntegrityReport): string {
  if (!report) return '—'
  const parts: string[] = []
  if (report.misaligned_count > 0) parts.push(`${report.misaligned_count} misaligned`)
  if (report.missing_count > 0) parts.push(`${report.missing_count} gap${report.missing_count > 1 ? 's' : ''}`)
  return parts.length ? parts.join(' · ') : 'OK'
}

export function integrityColorClass(report?: IntegrityReport): string {
  if (!report) return ''
  const total = report.misaligned_count + report.missing_count
  if (total === 0) return 'integrity-ok'
  if (total <= 10) return 'integrity-warn'
  return 'integrity-error'
}
