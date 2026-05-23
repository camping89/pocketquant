/**
 * Strategy-related domain types for chart markers and open position price lines.
 */

/** A single entry or exit trade event from the live strategy. */
export interface Trade {
  /** ISO timestamp of the trade event */
  timestamp: string
  /** long = bought, short = sold */
  side: 'long' | 'short'
  /** true = entry event, false = exit/close event */
  is_entry: boolean
  qty: number
  price: number
}

/** Current open position for a strategy subscription. */
export interface OpenPosition {
  side: 'long' | 'short'
  entry_price: number
  /** Liquidation price; null when no leverage or not provided by exchange. */
  liq_price: number | null
  /** Leverage multiplier (1 = spot / no leverage). */
  leverage: number
  qty: number
}
