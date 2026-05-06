// SSE payload shape from GET /api/v1/quotes/stream/{exchange}/{symbol}
export interface QuoteStreamPayload {
  symbol: string
  exchange: string
  last_price: number
  bid: number | null
  ask: number | null
  volume: number | null
  change: number | null
  change_percent: number | null
  ts: string
}
