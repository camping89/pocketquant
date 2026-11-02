import { apiDelete, apiFetch, apiFetchAdmin, apiPatch, apiPost } from './api-client'
import type { Broker } from '../lib/money-hint'

export { ApiError } from './api-client'

export type RunState = 'running' | 'stopped'
export type ManualAction = 'close' | 'cancel'

// One bar decided by the strategy, or a manual-action attempt when interval is null.
export interface SnapshotEntry {
  bar_start: string
  interval: string | null
  readings: { interval: string; name: string; value: unknown; ok: boolean | null }[]
  decision: { action: string; reason: string } | null
  // no_signal, sent, skipped:<reason>, accepted or rejected:<code>.
  outcome: string
  // price is the stop price of the resting entry order.
  pending: { side: string; price: number } | null
}

export interface SubscriptionPosition {
  direction: 'LONG' | 'SHORT'
  quantity: number
  entry_price: number
  sl_price: number | null
  tp_price: number | null
  unrealized_pnl: number
}

// The trader's last attempt at a manual action; outcome is accepted or rejected:<code>.
export interface ManualActionOutcome {
  action: ManualAction
  outcome: string
  at: string
}

export interface SubscriptionOrder {
  id: string
  side: string
  order_type: string
  status: string
  quantity: number
  price: number | null
  stop_price: number | null
  sl_price: number | null
  tp_price: number | null
  filled_price: number | null
  created_at: string
  updated_at: string
}

export interface Subscription {
  id: string
  strategy_code: string
  symbol: string
  // Lowest first; the first is the entry interval.
  intervals: string[]
  parameters: Record<string, unknown>
  created_at: string
  // Written by start/stop; the reconcile loop converges actual_state toward it.
  desired_state: RunState
  actual_state: RunState
  // Same as actual_state === 'running'; kept for back-compat.
  is_running: boolean
  // Fixed at create time; exness sends real orders.
  broker: Broker
  position: SubscriptionPosition | null
  // Latest ring entry.
  snapshot: SnapshotEntry | null
  // Set while a requested action waits for the trader.
  manual_action: ManualAction | null
  manual_action_outcome: ManualActionOutcome | null
}

export async function listSubscriptions(strategyCode?: string): Promise<Subscription[]> {
  const qs = strategyCode ? `?strategy_code=${encodeURIComponent(strategyCode)}` : ''
  return apiFetchAdmin<Subscription[]>(`/api/v1/subscriptions/${qs}`)
}

export async function addSymbol(
  strategyCode: string,
  body: { symbol: string; intervals: string[]; parameters: Record<string, unknown>; broker: Broker },
): Promise<Subscription> {
  return apiPost<Subscription>(`/api/v1/strategies/${strategyCode}/subscriptions`, body)
}

export async function editSubscription(
  subId: string,
  body: { intervals: string[]; parameters: Record<string, unknown> },
): Promise<Subscription> {
  return apiPatch<Subscription>(`/api/v1/subscriptions/${subId}`, body)
}

export async function requestAction(subId: string, action: ManualAction): Promise<void> {
  await apiPost(`/api/v1/subscriptions/${subId}/${action}`, {})
}

// Oldest first.
export async function fetchSnapshot(subId: string): Promise<SnapshotEntry[]> {
  return apiFetchAdmin<SnapshotEntry[]>(`/api/v1/subscriptions/${subId}/snapshot`)
}

export async function fetchOrders(subId: string): Promise<SubscriptionOrder[]> {
  return apiFetchAdmin<SubscriptionOrder[]>(`/api/v1/subscriptions/${subId}/orders`, { limit: '50' })
}

export async function fetchStrategyDefaults(code: string): Promise<Record<string, unknown>> {
  const doc = await apiFetch<{ parameters?: Record<string, unknown> }>(
    `/api/v1/strategies/${encodeURIComponent(code)}`,
  )
  return doc.parameters ?? {}
}

export async function removeSubscription(subId: string): Promise<void> {
  return apiDelete(`/api/v1/subscriptions/${subId}`)
}
