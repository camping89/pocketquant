import { apiPost, apiFetch } from './api-client'
import type { IntegrityReport, RepairResult, JobInfo } from '../types/market-data'

export async function checkIntegrity(
  symbol: string,
  interval: string,
  daysBack = 7,
): Promise<IntegrityReport> {
  return apiPost('/api/v1/market-data/integrity/check', {
    symbol,
    interval,
    days_back: daysBack,
  })
}

export async function repairIntegrity(
  symbol: string,
  interval: string,
  daysBack = 7,
): Promise<RepairResult> {
  return apiPost('/api/v1/market-data/integrity/repair', {
    symbol,
    interval,
    days_back: daysBack,
  })
}

export async function fetchJobs(): Promise<JobInfo[]> {
  return apiFetch('/api/v1/system/jobs')
}
