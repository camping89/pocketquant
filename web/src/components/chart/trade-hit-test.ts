import type { TradeMarker, TradeRow } from '../../api/backtest-api'
import { toUTCTimestamp } from '../../api/market-data-api'

/** Pick the trade whose time-span contains `timeSec`. Overlapping spans (multiple
 *  concurrent positions) are disambiguated by nearest entry price to the click.
 *  Returns null when the point falls outside every span — a click to deselect.
 *  Open trades (no exit_time) span to `lastCandleTime`. */
export function pickTradeAtTime(
  markers: TradeMarker[],
  timeSec: number,
  price: number | null,
  lastCandleTime: number | null,
): TradeMarker | null {
  let best: TradeMarker | null = null
  let bestGap = Infinity
  for (const m of markers) {
    const entry = toUTCTimestamp(m.entry_time) as number
    const exit = m.exit_time != null ? (toUTCTimestamp(m.exit_time) as number) : lastCandleTime
    if (exit == null || timeSec < entry || timeSec > exit) continue
    const gap = price == null ? 0 : Math.abs(price - m.entry_price)
    if (gap < bestGap) {
      bestGap = gap
      best = m
    }
  }
  return best
}

/** Build the full TradeRow the chart box + table-row highlight consume from an
 *  enriched marker. `duration_seconds` is derived (the marker doesn't carry it). */
export function tradeMarkerToRow(m: TradeMarker): TradeRow {
  const entry = toUTCTimestamp(m.entry_time) as number
  const exit = m.exit_time != null ? (toUTCTimestamp(m.exit_time) as number) : null
  return {
    trade_id: m.trade_id,
    direction: m.direction,
    entry_price: m.entry_price,
    entry_time: m.entry_time,
    exit_price: m.exit_price,
    exit_time: m.exit_time,
    quantity: m.quantity,
    sl_price: m.sl_price,
    tp_price: m.tp_price,
    pnl: m.pnl,
    commission: m.commission,
    duration_seconds: exit != null ? exit - entry : 0,
  }
}
