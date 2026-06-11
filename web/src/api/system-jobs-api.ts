import { apiFetch } from './api-client'
import type { JobRun, JobStats } from '../types/job-history'

export interface FetchRunsParams {
  limit?: number
  offset?: number
  status?: string
  since?: string
  until?: string
}

export async function fetchRuns(jobId: string, params: FetchRunsParams = {}): Promise<JobRun[]> {
  const qp: Record<string, string> = {}
  if (params.limit !== undefined) qp.limit = String(params.limit)
  if (params.offset !== undefined) qp.offset = String(params.offset)
  if (params.status) qp.status = params.status
  if (params.since) qp.since = params.since
  if (params.until) qp.until = params.until
  return apiFetch(`/api/v1/system/jobs/${encodeURIComponent(jobId)}/runs`, qp)
}

export async function fetchStats(
  jobId: string,
  window: '24h' | '7d' | '30d' = '24h',
): Promise<JobStats> {
  return apiFetch(`/api/v1/system/jobs/${encodeURIComponent(jobId)}/stats`, { window })
}
