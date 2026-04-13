import type { JobInfo, SyncStatus } from '../../types/market-data'
import { INTERVAL_MS } from './format-helpers'

type PillVariant = 'ok' | 'warn' | 'error' | 'neutral'

function syncHealth(statuses: SyncStatus[]): { variant: PillVariant; label: string } {
  if (!statuses.length) return { variant: 'neutral', label: 'Syncs: —' }
  let fresh = 0
  let hasError = false
  for (const s of statuses) {
    if (s.error_message) { hasError = true; continue }
    if (s.last_bar_at) {
      const age = Date.now() - new Date(s.last_bar_at.endsWith('Z') ? s.last_bar_at : s.last_bar_at + 'Z').getTime()
      const ivMs = INTERVAL_MS[s.interval] ?? 300_000
      if (age < ivMs * 2) fresh++
    }
  }
  if (hasError) return { variant: 'error', label: `Syncs: ${fresh}/${statuses.length} fresh` }
  if (fresh === statuses.length) return { variant: 'ok', label: `Syncs: ${fresh}/${statuses.length} fresh` }
  return { variant: 'warn', label: `Syncs: ${fresh}/${statuses.length} fresh` }
}

function integrityHealth(totals: { misaligned: number; gaps: number } | null): { variant: PillVariant; label: string } {
  if (!totals) return { variant: 'neutral', label: 'Data: —' }
  const total = totals.misaligned + totals.gaps
  if (total === 0) return { variant: 'ok', label: 'Data: 0 issues' }
  if (total <= 10) return { variant: 'warn', label: `Data: ${total} issues` }
  return { variant: 'error', label: `Data: ${total} issues` }
}

function jobHealth(jobs: JobInfo[]): { variant: PillVariant; label: string } {
  if (!jobs.length) return { variant: 'neutral', label: 'Jobs: —' }
  let ok = 0
  for (const j of jobs) {
    if (j.last_run?.status === 'failed') return { variant: 'error', label: `Jobs: failed` }
    if (j.next_run) {
      const overdue = Date.now() - new Date(j.next_run.endsWith('Z') ? j.next_run : j.next_run + 'Z').getTime()
      if (overdue > 300_000) return { variant: 'error', label: `Jobs: overdue` }
      if (overdue > 60_000) continue
    }
    ok++
  }
  if (ok === jobs.length) return { variant: 'ok', label: `Jobs: ${ok}/${jobs.length}` }
  return { variant: 'warn', label: `Jobs: ${ok}/${jobs.length}` }
}

interface HealthBannerProps {
  syncStatuses: SyncStatus[]
  jobs: JobInfo[]
  integrityTotals: { misaligned: number; gaps: number } | null
}

export function HealthBanner({ syncStatuses, jobs, integrityTotals }: HealthBannerProps) {
  const pills = [
    syncHealth(syncStatuses),
    integrityHealth(integrityTotals),
    jobHealth(jobs),
  ]

  return (
    <div className="health-banner">
      {pills.map((p, i) => (
        <div key={i} className={`health-pill health-pill--${p.variant}`}>
          <span className="health-pill-dot" />
          {p.label}
        </div>
      ))}
    </div>
  )
}
