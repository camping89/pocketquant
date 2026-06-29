import { apiFetch, apiPost, ApiError } from './api-client'

export { ApiError } from './api-client'

/** Reconcile-loop run state: desired = what the user asked for, actual = live truth. */
export type RunState = 'running' | 'stopped'

export interface Subscription {
  id: string
  strategy_code: string
  /** Composite symbol string: "{CODE}:{EXCHANGE}" e.g. "BTCUSDT:BINANCE" */
  symbol: string
  interval: string
  created_at: string
  /** Target state written by start/stop; reconcile converges actual toward it. */
  desired_state: RunState
  /** Reconcile loop's mirror of live engine state. */
  actual_state: RunState
  /** Derived: actual_state === 'running'. Kept for back-compat. */
  is_running: boolean
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
  const res = await fetch(`/api/v1/subscriptions/${subId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new ApiError(`DELETE subscription failed: ${res.status}`, res.status)
}

export async function deleteStrategy(strategyCode: string): Promise<void> {
  const res = await fetch(`/api/v1/strategies/${strategyCode}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new ApiError(`DELETE strategy failed: ${res.status}`, res.status)
}
