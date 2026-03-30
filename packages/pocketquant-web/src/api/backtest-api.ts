import { apiFetch } from './api-client'

export interface BacktestTrade {
  side: string
  price: number
  quantity: number
  pnl: number
  commission: number
  timestamp: string
}

export interface BacktestMetrics {
  total_return: number
  sharpe_ratio: number
  max_drawdown: number
  win_rate: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  total_commission: number
}

export interface BacktestResponse {
  run_id: string
  status: string
  metrics: BacktestMetrics | null
  trades: BacktestTrade[]
}

export async function fetchStrategies(): Promise<string[]> {
  return apiFetch<string[]>('/api/v1/backtest/strategies')
}

export async function runBacktest(params: {
  strategy_id: string
  symbol: string
  exchange: string
  interval: string
  start_date: string
  end_date: string
  initial_capital?: number
}): Promise<BacktestResponse> {
  const res = await fetch('/api/v1/backtest/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      initial_capital: 10_000,
      ...params,
    }),
  })
  if (!res.ok) throw new Error(`Backtest failed: ${res.status}`)
  return res.json()
}
