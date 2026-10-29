export interface Trade {
  timestamp: string
  side: 'long' | 'short'
  is_entry: boolean
  qty: number
  price: number
}

export interface OpenPosition {
  side: 'long' | 'short'
  entry_price: number
  // null when there is no leverage or the exchange does not provide it.
  liq_price: number | null
  // 1 = spot / no leverage.
  leverage: number
  qty: number
}
