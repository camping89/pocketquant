import { useMemo, useState, type CSSProperties } from 'react'
import { useBacktestOrders, useBacktestMarkers } from '../../hooks/use-backtest-run'
import type { BacktestOrder } from '../../api/backtest-api'
import { formatQty } from '../../lib/number-format'
import { OrderDetailDrawer } from './order-detail-drawer'

const th: CSSProperties = {
  textAlign: 'left',
  padding: '6px 10px',
  color: 'var(--text-secondary)',
  fontWeight: 600,
  borderBottom: '1px solid var(--border-color)',
}
const td: CSSProperties = { padding: '6px 10px', borderBottom: '1px solid var(--border-color)' }

type OrderRole = { action: 'Entry' | 'Exit' | '—'; direction: 'LONG' | 'SHORT' | null }

/** Classify a raw order as opening (Entry) or closing (Exit) its trade, using the
 *  trade's direction: a LONG is opened by a BUY and closed by a SELL; a SHORT is
 *  the reverse. Orders with no resulting trade (cancelled/rejected/unfilled) stay
 *  unclassified — the raw side is still visible in the detail drawer. */
function deriveRole(
  o: BacktestOrder,
  dirByTrade: Map<string, 'LONG' | 'SHORT'>,
): OrderRole {
  const dir = o.resulting_trade_id ? dirByTrade.get(o.resulting_trade_id) : undefined
  if (!dir) return { action: '—', direction: null }
  const isEntry = (dir === 'LONG' && o.side === 'BUY') || (dir === 'SHORT' && o.side === 'SELL')
  return { action: isEntry ? 'Entry' : 'Exit', direction: dir }
}

/** Orders for a run — fetched lazily once ``active`` (the tab is open). Row opens
 *  a drawer with fills + events. Entry/Exit + Long/Short are derived by joining
 *  each order to its trade's direction (trade-markers, shared with the chart). */
export function OrdersTable({ runId, active }: { runId: string; active: boolean }) {
  const { data: orders, isLoading, error } = useBacktestOrders(runId, active)
  const { data: markers } = useBacktestMarkers(runId, active)
  const [selected, setSelected] = useState<BacktestOrder | null>(null)

  const dirByTrade = useMemo(() => {
    const m = new Map<string, 'LONG' | 'SHORT'>()
    for (const t of markers ?? []) m.set(t.trade_id, t.direction)
    return m
  }, [markers])

  if (isLoading) return <div className="empty-state" style={{ padding: 16 }}>Loading orders…</div>
  if (error) return <div className="empty-state empty-state--error" style={{ padding: 16 }}>Failed to load orders: {(error as Error).message}</div>
  if (!orders || orders.length === 0) return <div className="empty-state" style={{ padding: 16 }}>No orders for this run.</div>

  return (
    <>
      <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse', color: 'var(--text-primary)' }}>
        <thead>
          <tr>
            <th style={th}>Submitted</th>
            <th style={th}>Action</th>
            <th style={th}>Direction</th>
            <th style={th}>Type</th>
            <th style={{ ...th, textAlign: 'right' }}>Qty</th>
            <th style={th}>Status</th>
            <th style={{ ...th, textAlign: 'right' }}>Fills</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((o) => {
            const { action, direction } = deriveRole(o, dirByTrade)
            const dirColor = direction === 'LONG' ? 'var(--up-color)' : direction === 'SHORT' ? 'var(--down-color)' : 'var(--text-secondary)'
            return (
              <tr
                key={o.order_id}
                onClick={() => setSelected(o)}
                style={{ cursor: 'pointer' }}
              >
                <td style={td}>{o.submitted_at.replace('T', ' ').slice(0, 19)}</td>
                <td style={td}>{action}</td>
                <td style={{ ...td, color: dirColor }}>{direction ?? '—'}</td>
                <td style={td}>{o.order_type}</td>
                <td style={{ ...td, textAlign: 'right' }}>{formatQty(o.quantity)}</td>
                <td style={td}>{o.status}</td>
                <td style={{ ...td, textAlign: 'right' }}>{o.fills.length}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <OrderDetailDrawer order={selected} onClose={() => setSelected(null)} />
    </>
  )
}
