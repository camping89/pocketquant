/**
 * Compact table showing last N trades for the selected strategy subscription.
 * Accepts a generic trade shape; renders direction, entry/exit price, pnl.
 */
import { useFmt } from '../../lib/use-timezone'

export interface StrategyTrade {
  id: string
  direction: 'LONG' | 'SHORT'
  entry_price: number
  exit_price: number | null
  entry_time: string
  exit_time: string | null
  pnl: number
  quantity: number
}

interface RecentTradesTableProps {
  trades: StrategyTrade[]
  isLoading?: boolean
}

function fmtPrice(v: number | null): string {
  if (v == null) return '—'
  return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}

const thStyle: React.CSSProperties = {
  padding: '5px 8px',
  background: 'var(--bg-primary)',
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  fontSize: 10,
  letterSpacing: '0.04em',
  fontWeight: 600,
  textAlign: 'left',
  borderBottom: '1px solid var(--border-color)',
  position: 'sticky',
  top: 0,
  userSelect: 'none',
}

const tdStyle: React.CSSProperties = {
  padding: '5px 8px',
  fontSize: 11,
  borderBottom: '1px solid rgba(255,255,255,0.03)',
  fontVariantNumeric: 'tabular-nums',
}

export function RecentTradesTable({ trades, isLoading = false }: RecentTradesTableProps) {
  const fmt = useFmt()
  if (isLoading) {
    return (
      <div style={{ padding: '12px 0', color: 'var(--text-secondary)', fontSize: 12 }}>
        Loading trades…
      </div>
    )
  }

  if (trades.length === 0) {
    return (
      <div className="empty-state">No trades yet.</div>
    )
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
        <thead>
          <tr>
            <th style={thStyle}>Dir</th>
            <th style={{ ...thStyle, textAlign: 'right' }}>Entry</th>
            <th style={{ ...thStyle, textAlign: 'right' }}>Exit</th>
            <th style={{ ...thStyle, textAlign: 'right' }}>Qty</th>
            <th style={{ ...thStyle, textAlign: 'right' }}>PnL</th>
            <th style={thStyle}>Time</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr key={t.id}>
              <td style={tdStyle}>
                <span
                  className={`direction-badge direction-badge--${t.direction.toLowerCase()}`}
                >
                  {t.direction}
                </span>
              </td>
              <td style={{ ...tdStyle, textAlign: 'right' }}>{fmtPrice(t.entry_price)}</td>
              <td style={{ ...tdStyle, textAlign: 'right' }}>{fmtPrice(t.exit_price)}</td>
              <td style={{ ...tdStyle, textAlign: 'right' }}>{t.quantity}</td>
              <td
                style={{
                  ...tdStyle,
                  textAlign: 'right',
                  color: t.pnl >= 0 ? 'var(--up-color)' : 'var(--down-color)',
                }}
              >
                {t.pnl >= 0 ? '+' : ''}{t.pnl.toFixed(2)}
              </td>
              <td style={{ ...tdStyle, color: 'var(--text-secondary)' }}>
                {fmt.barDate(t.entry_time)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
