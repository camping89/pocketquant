import { useEffect, useRef } from 'react'
import type { BacktestOrder } from '../../api/backtest-api'
import { formatPrice, formatQty } from '../../lib/number-format'

interface OrderDetailDrawerProps {
  order: BacktestOrder | null
  onClose: () => void
}

function fmtTime(iso: string): string {
  return iso.replace('T', ' ').slice(0, 19)
}

/** Side drawer for one order — its fills[] and lifecycle events[], plus a link
 *  hint to the resulting trade. Keyed by order_id (Phase 1 DTO). */
export function OrderDetailDrawer({ order, onClose }: OrderDetailDrawerProps) {
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!order) return
    closeRef.current?.focus()
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [order, onClose])

  if (!order) return null

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} aria-hidden />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={`Order ${order.order_id}`}>
        <header className="drawer-header">
          <span className="drawer-title">{order.side} {order.order_type}</span>
          <button ref={closeRef} className="drawer-close" onClick={onClose} aria-label="Close">×</button>
        </header>

        <dl className="drawer-meta">
          <dt>Order ID</dt><dd style={{ fontFamily: 'monospace', fontSize: 11 }}>{order.order_id}</dd>
          <dt>Status</dt><dd>{order.status}</dd>
          <dt>Quantity</dt><dd>{formatQty(order.quantity)}</dd>
          <dt>SL / TP</dt><dd>{formatPrice(order.sl_price)} / {formatPrice(order.tp_price)}</dd>
          <dt>Resulting trade</dt>
          <dd style={{ fontFamily: 'monospace', fontSize: 11 }}>{order.resulting_trade_id ?? '—'}</dd>
        </dl>

        <h4 style={{ fontSize: 12, color: 'var(--text-secondary)', margin: '12px 16px 4px' }}>Fills ({order.fills.length})</h4>
        <div style={{ padding: '0 16px' }}>
          {order.fills.length === 0 ? (
            <div className="empty-state" style={{ padding: 8 }}>No fills.</div>
          ) : (
            order.fills.map((f) => (
              <div key={f.fill_id} style={{ fontSize: 12, padding: '4px 0', borderBottom: '1px solid var(--border-color)' }}>
                {fmtTime(f.timestamp)} · {formatQty(f.quantity)} @ {formatPrice(f.price)} · fee {f.commission.toFixed(4)}
              </div>
            ))
          )}
        </div>

        <h4 style={{ fontSize: 12, color: 'var(--text-secondary)', margin: '12px 16px 4px' }}>Events ({order.events.length})</h4>
        <div style={{ padding: '0 16px 16px' }}>
          {order.events.length === 0 ? (
            <div className="empty-state" style={{ padding: 8 }}>No events.</div>
          ) : (
            order.events.map((e, i) => (
              <div key={i} style={{ fontSize: 12, padding: '4px 0', borderBottom: '1px solid var(--border-color)' }}>
                {fmtTime(e.timestamp)} · {e.from_status ?? '∅'} → {e.to_status}{e.reason ? ` (${e.reason})` : ''}
              </div>
            ))
          )}
        </div>
      </aside>
    </>
  )
}
