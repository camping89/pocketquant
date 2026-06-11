import { apiFetch } from './api-client'

export interface BacktestPosition {
  direction: 'LONG' | 'SHORT'
  entry_price: number
  entry_time: string
  exit_price: number | null
  exit_time: string | null
  quantity: number
  sl_price: number | null
  tp_price: number | null
  pnl: number
  commission: number
  symbol?: string
}

export interface BacktestMetrics {
  total_return: number
  cagr: number
  sharpe_ratio: number
  sortino_ratio: number
  max_drawdown: number
  win_rate: number
  profit_factor: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  avg_win: number
  avg_loss: number
  avg_trade_duration_seconds: number | null
  total_commission: number
}

export interface EquityPoint {
  timestamp: string
  equity: number
  drawdown: number
}

export type BacktestStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface SubscriptionBacktest {
  _id?: string
  subscription_id?: string
  strategy_code?: string
  status: BacktestStatus | string
  metrics: BacktestMetrics | null
  positions: BacktestPosition[]
  equity_curve: EquityPoint[]
  config_snapshot?: Record<string, unknown>
  trades?: unknown[]
  started_at?: string
  completed_at?: string
  last_run_at?: string | null
  error_message?: string | null
  error_msg?: string | null
  parameters?: Record<string, unknown>
}

export async function fetchStrategies(): Promise<string[]> {
  return apiFetch<string[]>('/api/v1/backtest/strategies')
}
