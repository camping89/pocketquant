import { apiFetch, apiPost } from './api-client'

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

export type BacktestStatus = 'started' | 'finished' | 'failed'

/** A single ad-hoc backtest run. ``positions`` is assembled client-side from the
 *  trades endpoint + the run doc's open lots — the run doc itself is slim. */
export interface BacktestRunResult {
  id?: string
  strategy_code?: string
  status: BacktestStatus | string
  metrics: BacktestMetrics | null
  positions: BacktestPosition[]
  equity_curve: EquityPoint[]
  config_snapshot?: Record<string, unknown>
  error_message?: string | null
  error_msg?: string | null
  started_at?: string
  completed_at?: string
  parameters?: Record<string, unknown>
}

export interface RunBacktestBody {
  strategy_id: string
  symbol: string
  interval: string
  start_date: string
  end_date: string
  initial_capital?: number
  slippage_bps?: number
  commission_bps?: number
  parameters?: Record<string, unknown>
}

interface BacktestRunDoc {
  _id?: string
  status: BacktestStatus | string
  strategy_code?: string
  metrics: BacktestMetrics | null
  equity_curve?: EquityPoint[]
  open_positions?: Array<{
    direction: 'LONG' | 'SHORT'
    entry_price: number
    entry_time: string
    quantity: number
    sl_price: number | null
    tp_price: number | null
    entry_commission_portion?: number
    symbol?: string
  }>
  config_snapshot?: Record<string, unknown>
  error_message?: string | null
  started_at?: string
  completed_at?: string
  parameters?: Record<string, unknown>
}

interface BacktestTrade {
  direction: 'LONG' | 'SHORT'
  entry_price: number
  entry_time: string
  exit_price: number
  exit_time: string | null
  quantity: number
  sl_price: number | null
  tp_price: number | null
  pnl: number
  commission: number
}

export async function fetchStrategies(): Promise<string[]> {
  return apiFetch<string[]>('/api/v1/backtest/strategies')
}

export async function runBacktest(body: RunBacktestBody): Promise<{ request_id: string }> {
  return apiPost<{ request_id: string }>('/api/v1/backtest/run', body)
}

/** Fetch a run + join its closed trades into the unified ``positions`` list.
 *  Trades are only queried once the run is terminal (no point while ``started``). */
export async function fetchBacktestRun(runId: string): Promise<BacktestRunResult> {
  const doc = await apiFetch<BacktestRunDoc>(`/api/v1/backtest/${runId}`)
  const positions: BacktestPosition[] = []
  if (doc.status === 'finished') {
    const { trades } = await apiFetch<{ trades: BacktestTrade[] }>(
      `/api/v1/backtest/${runId}/trades`,
    )
    for (const t of trades) {
      positions.push({
        direction: t.direction,
        entry_price: t.entry_price,
        entry_time: t.entry_time,
        exit_price: t.exit_price,
        exit_time: t.exit_time,
        quantity: t.quantity,
        sl_price: t.sl_price,
        tp_price: t.tp_price,
        pnl: t.pnl,
        commission: t.commission,
      })
    }
    for (const ol of doc.open_positions ?? []) {
      positions.push({
        direction: ol.direction,
        entry_price: ol.entry_price,
        entry_time: ol.entry_time,
        exit_price: null,
        exit_time: null,
        quantity: ol.quantity,
        sl_price: ol.sl_price,
        tp_price: ol.tp_price,
        pnl: 0,
        commission: ol.entry_commission_portion ?? 0,
      })
    }
  }
  return {
    id: doc._id,
    strategy_code: doc.strategy_code,
    status: doc.status,
    metrics: doc.metrics,
    positions,
    equity_curve: doc.equity_curve ?? [],
    config_snapshot: doc.config_snapshot,
    error_message: doc.error_message,
    started_at: doc.started_at,
    completed_at: doc.completed_at,
    parameters: doc.parameters,
  }
}
