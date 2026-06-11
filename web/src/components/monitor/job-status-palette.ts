import type { JobRunStatus } from '../../types/job-history'

export const STATUS_COLOR: Record<JobRunStatus, string> = {
  completed: '#10b981',
  running: '#38bdf8',
  missed: '#fbbf24',
  skipped_max_instances: '#f59e0b',
  failed: '#f43f5e',
  stuck: '#d946ef',
  error: '#f43f5e',
}

export const STATUS_LABEL: Record<JobRunStatus, string> = {
  completed: 'OK',
  running: 'running',
  missed: 'missed',
  skipped_max_instances: 'skipped',
  failed: 'failed',
  stuck: 'stuck',
  error: 'error',
}

export function statusColor(status: string): string {
  return STATUS_COLOR[(status as JobRunStatus)] ?? '#94a3b8'
}

export function statusLabel(status: string): string {
  return STATUS_LABEL[(status as JobRunStatus)] ?? status
}
