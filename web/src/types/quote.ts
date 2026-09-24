// SSE payload shape from GET /api/v1/quotes/stream/{symbol}
export interface QuoteStreamPayload {
  /** Composite symbol string: "{CODE}:{EXCHANGE}" e.g. "BTCUSDT:BINANCE" or "ES1!:CME_MINI" */
  symbol: string
  last_price: number
  bid: number | null
  ask: number | null
  volume: number | null
  change: number | null
  change_percent: number | null
  ts: string
}
