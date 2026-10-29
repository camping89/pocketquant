import { apiDelete, apiFetch, apiPost } from './api-client'

export { ApiError } from './api-client'

export type RunState = 'running' | 'stopped'

export interface Subscription {
  id: string
  strategy_code: string
  symbol: string
  interval: string
  created_at: string
  // Written by start/stop; the reconcile loop converges actual_state toward it.
  desired_state: RunState
  actual_state: RunState
  // Same as actual_state === 'running'; kept for back-compat.
  is_running: boolean
  // Fixed at create time; exness sends real orders.
  broker: 'paper' | 'exness'
}

export async function listSubscriptions(strategyCode?: string): Promise<Subscription[]> {
  const qs = strategyCode ? `?strategy_code=${encodeURIComponent(strategyCode)}` : ''
  return apiFetch<Subscription[]>(`/api/v1/subscriptions/${qs}`)
}

export async function addSymbol(
  strategyCode: string,
  body: { symbol: string; interval: string },
): Promise<Subscription> {
  return apiPost<Subscription>(`/api/v1/strategies/${strategyCode}/subscriptions`, body)
}

export async function removeSubscription(subId: string): Promise<void> {
  return apiDelete(`/api/v1/subscriptions/${subId}`)
}
