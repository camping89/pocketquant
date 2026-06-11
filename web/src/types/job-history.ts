export type JobRunStatus =
  | 'completed'
  | 'running'
  | 'missed'
  | 'skipped_max_instances'
  | 'failed'
  | 'stuck'
  | 'error'

export interface JobRunDetail {
  symbol: string
  exchange: string
  interval: string
  bars_fetched: number
  bars_inserted: number
  filtered_existing: number
  filtered_misaligned: number
  status: string
  error: string | null
  ts: string | null
}

export interface JobRun {
  _id: string
  job_id: string
  started_at: string | null
  finished_at: string | null
  scheduled_run_time: string | null
  duration_ms: number | null
  status: JobRunStatus
  error: string | null
  total_inserted: number | null
  total_fetched: number | null
  details: JobRunDetail[]
}

export interface JobStats {
  window: '24h' | '7d' | '30d'
  by_status: Partial<Record<JobRunStatus, number>>
  p50_ms: number | null
  p95_ms: number | null
}
