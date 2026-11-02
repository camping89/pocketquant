// Every text a subscription row or drawer shows, as pure functions so tests cover them.
import { ApiError } from '../api/api-client'
import type {
  ManualAction,
  ManualActionOutcome,
  SnapshotEntry,
  SubscriptionOrder,
  SubscriptionPosition,
} from '../api/strategy-api'
import type { StrategyTrade } from '../hooks/use-strategy-trades'
import { formatPrice, formatQty } from './number-format'

export function positionText(pos: SubscriptionPosition | null): string {
  if (!pos) return '-'
  let text = `${pos.direction} ${formatQty(pos.quantity)} @ ${formatPrice(pos.entry_price)}`
  if (pos.sl_price != null) text += ` SL ${formatPrice(pos.sl_price)}`
  if (pos.tp_price != null) text += ` TP ${formatPrice(pos.tp_price)}`
  return text
}

export function pendingText(pending: SnapshotEntry['pending']): string {
  if (!pending) return '-'
  return `${pending.side.toUpperCase()} STOP @ ${formatPrice(pending.price)}`
}

// A null interval marks a manual-action attempt recorded in the ring.
export function decisionText(entry: SnapshotEntry | null): string {
  if (!entry) return '-'
  if (entry.interval === null) return `manual action (${entry.outcome})`
  const base = entry.decision ? `${entry.decision.action} - ${entry.decision.reason}` : '-'
  return entry.outcome === 'no_signal' ? base : `${base} (${entry.outcome})`
}

export function manualActionText(
  queued: ManualAction | null,
  last: ManualActionOutcome | null,
): string {
  if (queued) return `${queued} requested - runs when the trader holds the lease`
  if (!last) return ''
  if (last.outcome.startsWith('rejected:')) {
    return `${last.action} ${last.outcome} - press again to retry`
  }
  return `${last.action} ${last.outcome}`
}

export interface ParameterRow {
  key: string
  def: unknown
  value: unknown
  // A key the strategy does not declare.
  extra: boolean
}

export function parameterRows(
  defaults: Record<string, unknown>,
  values: Record<string, unknown>,
): ParameterRow[] {
  const rows: ParameterRow[] = Object.keys(defaults).map((key) => ({
    key,
    def: defaults[key],
    value: key in values ? values[key] : defaults[key],
    extra: false,
  }))
  for (const key of Object.keys(values)) {
    if (!(key in defaults)) rows.push({ key, def: undefined, value: values[key], extra: true })
  }
  return rows
}

// The only client-side check: the text must parse to be sent. Value rules are the backend's.
export function parseParameters(
  text: string,
): { value: Record<string, unknown> } | { error: string } {
  if (!text.trim()) return { value: {} }
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch (e) {
    return { error: `Parameters are not valid JSON: ${(e as Error).message}` }
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    return { error: 'Parameters must be a JSON object.' }
  }
  return { value: parsed as Record<string, unknown> }
}

export interface TimelineItem {
  at: string
  text: string
}

function orderText(o: SubscriptionOrder): string {
  const type = o.order_type === 'stop_market' ? 'STOP' : o.order_type.toUpperCase()
  const price = o.filled_price ?? o.stop_price ?? o.price
  let text = `${o.side.toUpperCase()} ${type} ${formatQty(o.quantity)}`
  if (price != null) text += ` @ ${formatPrice(price)}`
  if (o.sl_price != null) text += ` SL ${formatPrice(o.sl_price)}`
  if (o.tp_price != null) text += ` TP ${formatPrice(o.tp_price)}`
  return `${text} · ${o.status}`
}

function tradeText(t: StrategyTrade): string {
  return (
    `${t.direction} ${formatQty(t.quantity)} closed @ ${formatPrice(t.exit_price)}` +
    ` (entry ${formatPrice(t.entry_price)}, PnL ${t.pnl.toFixed(2)})`
  )
}

// ISO strings from one backend share a format, so they sort as text.
export function timeline(orders: SubscriptionOrder[], trades: StrategyTrade[]): TimelineItem[] {
  const items: TimelineItem[] = [
    ...orders.map((o) => ({ at: o.updated_at, text: orderText(o) })),
    ...trades.map((t) => ({ at: t.exit_time ?? t.entry_time, text: tradeText(t) })),
  ]
  return items.sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0))
}

export function errorText(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401) return 'Admin token required: reload the page and enter it.'
    if (err.code) return `${err.code}: ${err.message}`
  }
  return err instanceof Error ? err.message : String(err)
}
