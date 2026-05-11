import { apiFetch, apiPost } from './api-client'
import type { SubscriptionBacktest } from './backtest-api'

// Re-export so existing consumers importing from strategy-api continue to work.
export type { SubscriptionBacktest } from './backtest-api'

// Custom error that carries HTTP status so callers can branch on 404 etc.
export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export interface SubscriptionBacktestStatus {
  status: 'running' | 'completed' | 'failed'
  last_run_at: string | null
  error_msg: string | null
}

export interface Subscription {
  id: string
  strategy_id: string
  symbol: string
  exchange: string
  interval: string
  created_at: string
  backtest: SubscriptionBacktestStatus | null
}

export async function listSymbols(strategyId: string): Promise<Subscription[]> {
  return apiFetch<Subscription[]>(`/api/v1/strategies/${strategyId}/symbols`)
}

export async function addSymbol(
  strategyId: string,
  body: { symbol: string; exchange: string; interval: string },
): Promise<Subscription> {
  return apiPost<Subscription>(`/api/v1/strategies/${strategyId}/symbols`, body)
}

export async function removeSymbol(strategyId: string, subId: string): Promise<void> {
  const res = await fetch(`/api/v1/strategies/${strategyId}/symbols/${subId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new ApiError(`DELETE symbol failed: ${res.status}`, res.status)
}

export async function runAllBacktests(strategyId: string): Promise<{ job_ids: string[] }> {
  return apiPost<{ job_ids: string[] }>(`/api/v1/strategies/${strategyId}/backtest/run-all`, {})
}

export async function getSubscriptionBacktest(
  strategyId: string,
  subId: string,
): Promise<SubscriptionBacktest> {
  const res = await fetch(`/api/v1/strategies/${strategyId}/symbols/${subId}/backtest`)
  if (!res.ok) throw new ApiError(`GET backtest failed: ${res.status}`, res.status)
  return res.json()
}

export async function deleteStrategy(strategyId: string): Promise<void> {
  const res = await fetch(`/api/v1/strategies/${strategyId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new ApiError(`DELETE strategy failed: ${res.status}`, res.status)
}
