import { useState, type CSSProperties } from 'react'
import { useBacktestOrders } from '../../hooks/use-backtest-run'
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

/** Orders for a run — fetched lazily once ``active`` (the tab is open). Row opens
 *  a drawer with fills + events. */
export function OrdersTable({ runId, active }: { runId: string; active: boolean }) {
  const { data: orders, isLoading, error } = useBacktestOrders(runId, active)
  const [selected, setSelected] = useState<BacktestOrder | null>(null)

  if (isLoading) return <div className="empty-state" style={{ padding: 16 }}>Loading orders…</div>
  if (error) return <div className="empty-state empty-state--error" style={{ padding: 16 }}>Failed to load orders: {(error as Error).message}</div>
  if (!orders || orders.length === 0) return <div className="empty-state" style={{ padding: 16 }}>No orders for this run.</div>

  return (
    <>
      <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse', color: 'var(--text-primary)' }}>
        <thead>
          <tr>
            <th style={th}>Submitted</th>
            <th style={th}>Side</th>
            <th style={th}>Type</th>
            <th style={{ ...th, textAlign: 'right' }}>Qty</th>
            <th style={th}>Status</th>
            <th style={{ ...th, textAlign: 'right' }}>Fills</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((o) => (
            <tr
              key={o.order_id}
              onClick={() => setSelected(o)}
              style={{ cursor: 'pointer' }}
            >
              <td style={td}>{o.submitted_at.replace('T', ' ').slice(0, 19)}</td>
              <td style={{ ...td, color: o.side === 'BUY' ? 'var(--up-color)' : 'var(--down-color)' }}>{o.side}</td>
              <td style={td}>{o.order_type}</td>
              <td style={{ ...td, textAlign: 'right' }}>{formatQty(o.quantity)}</td>
              <td style={td}>{o.status}</td>
              <td style={{ ...td, textAlign: 'right' }}>{o.fills.length}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <OrderDetailDrawer order={selected} onClose={() => setSelected(null)} />
    </>
  )
}
