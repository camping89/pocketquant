import { useRealtimeQuote } from '../../hooks/use-realtime-quote'
import { TickerStaleIndicator } from './ticker-stale-indicator'

interface TickerWidgetProps {
  exchange: string
  symbol: string
}

function formatPrice(price: number): string {
  if (price >= 1000) return price.toFixed(2)
  if (price >= 1) return price.toFixed(4)
  return price.toFixed(8)
}

function formatChange(change: number | null, pct: number | null): string {
  if (change === null || pct === null) return ''
  const arrow = change >= 0 ? '▲' : '▼'
  const sign = change >= 0 ? '+' : ''
  return `${arrow} ${sign}${change.toFixed(2)} (${sign}${pct.toFixed(2)}%)`
}

export function TickerWidget({ exchange, symbol }: TickerWidgetProps) {
  const { quote, lastUpdateTs } = useRealtimeQuote(exchange, symbol)

  const isLive = quote !== null
  // No data yet and no timestamp → symbol not tracked or not yet received
  const showEmpty = !isLive && lastUpdateTs === null

  const priceColor =
    quote !== null && quote.change !== null
      ? quote.change >= 0 ? '#26a69a' : '#ef5350'
      : '#e8e8f0'

  if (showEmpty) {
    return (
      <div className="ticker-widget ticker-widget--empty" style={containerStyle}>
        <TickerStaleIndicator lastUpdateTs={null} />
        <span style={{ color: '#8b8b9a', fontSize: 12 }}>
          Symbol not tracked. Add via admin.
        </span>
      </div>
    )
  }

  if (!isLive) {
    return (
      <div className="ticker-widget" style={containerStyle}>
        <TickerStaleIndicator lastUpdateTs={lastUpdateTs} />
        <span style={{ color: '#8b8b9a', fontSize: 12 }}>{symbol} — loading…</span>
      </div>
    )
  }

  return (
    <div className="ticker-widget" style={containerStyle}>
      <TickerStaleIndicator lastUpdateTs={lastUpdateTs} />
      <span style={{ color: '#8b8b9a', fontSize: 11, marginRight: 2 }}>{exchange}</span>
      <span style={{ fontWeight: 600, fontSize: 13, color: '#e8e8f0' }}>{symbol}</span>
      <span style={{ fontWeight: 700, fontSize: 14, color: priceColor, marginLeft: 6 }}>
        {formatPrice(quote.last_price)}
      </span>
      {quote.change !== null && (
        <span
          style={{
            fontSize: 12,
            color: priceColor,
            marginLeft: 6,
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {formatChange(quote.change, quote.change_percent)}
        </span>
      )}
    </div>
  )
}

const containerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  padding: '2px 10px',
  borderRadius: 4,
  background: 'rgba(255,255,255,0.04)',
  minWidth: 0,
  flexShrink: 0,
}
