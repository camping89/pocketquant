import { apiFetch, apiPost, apiPatch } from './api-client'

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
  /** Composite symbol / interval / window end — lifted from config_snapshot so a
   *  chart can anchor OHLCV to the exact backtest window without re-reading it. */
  symbol?: string
  interval?: string
  end_date?: string
  verdict?: string | null
  error_message?: string | null
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
  verdict?: string | null
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
  const cfg = doc.config_snapshot ?? {}
  return {
    id: doc._id,
    strategy_code: doc.strategy_code,
    status: doc.status,
    metrics: doc.metrics,
    positions,
    equity_curve: doc.equity_curve ?? [],
    config_snapshot: doc.config_snapshot,
    symbol: (cfg.symbol as string | undefined)?.toUpperCase(),
    interval: cfg.interval as string | undefined,
    end_date: cfg.end_date as string | undefined,
    verdict: doc.verdict,
    error_message: doc.error_message,
    started_at: doc.started_at,
    completed_at: doc.completed_at,
    parameters: doc.parameters,
  }
}

// --- History rail -----------------------------------------------------------

export interface BacktestRunRow {
  id: string
  strategy_code: string
  symbol: string
  interval: string
  status: BacktestStatus | string
  metrics: BacktestMetrics | null
  date_range: { start: string | null; end: string | null }
  verdict: string | null
  started_at: string
  completed_at: string
}

export interface BacktestRunScope {
  strategy: string
  /** Composite CODE:EXCHANGE (e.g. BTCUSDT:BINANCE), or undefined for strategy-wide. */
  symbol?: string
  interval?: string
}

/** History for a strategy, scoped by composite symbol + interval when provided.
 *  ``symbol`` MUST be composite — a bare code never matches a stored run. */
export async function listBacktestRuns(scope: BacktestRunScope): Promise<BacktestRunRow[]> {
  const params: Record<string, string> = { limit: '50' }
  if (scope.symbol) params.symbol = scope.symbol
  if (scope.interval) params.interval = scope.interval
  return apiFetch<BacktestRunRow[]>(`/api/v1/backtest/strategy/${scope.strategy}`, params)
}

/** Runs across ALL strategies, optionally narrowed by symbol/interval. There is
 *  no list-all endpoint by design (storage stays scoped) — fan out over the
 *  strategy registry and merge, then sort newest-first. */
export async function listAllBacktestRuns(
  scope: Omit<BacktestRunScope, 'strategy'> = {},
): Promise<BacktestRunRow[]> {
  const strategies = await fetchStrategies()
  const perStrategy = await Promise.all(
    strategies.map((strategy) => listBacktestRuns({ strategy, ...scope })),
  )
  return perStrategy
    .flat()
    .sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime())
}

// --- Orders -----------------------------------------------------------------

export interface OrderFill {
  fill_id: string
  side: string
  quantity: number
  price: number
  commission: number
  slippage: number
  timestamp: string
}

export interface OrderEvent {
  timestamp: string
  from_status: string | null
  to_status: string
  reason: string | null
}

export interface BacktestOrder {
  order_id: string
  side: string
  order_type: string
  quantity: number
  price: number | null
  sl_price: number | null
  tp_price: number | null
  status: string
  submitted_at: string
  last_updated_at: string
  resulting_trade_id: string | null
  fills: OrderFill[]
  events: OrderEvent[]
}

export async function fetchBacktestOrders(runId: string): Promise<BacktestOrder[]> {
  const { orders } = await apiFetch<{ orders: BacktestOrder[] }>(
    `/api/v1/backtest/${runId}/orders`,
  )
  return orders
}

// --- Verdict ----------------------------------------------------------------

export async function setVerdict(runId: string, verdict: string | null): Promise<void> {
  await apiPatch(`/api/v1/backtest/${runId}/verdict`, { verdict })
}
