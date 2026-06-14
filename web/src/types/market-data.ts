import type { UTCTimestamp } from 'lightweight-charts'

export interface OHLCVBar {
  id: string
  datetime: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface OHLCVResponse {
  symbol: string
  interval: string
  data: OHLCVBar[]
  count: number
}

/** Composite symbol string in the format "{CODE}:{EXCHANGE}" e.g. "BTCUSDT:BINANCE". */
export type SelectedSymbol = string

export interface SymbolInfo {
  symbol: string
  name: string
  asset_type: string
  is_active: boolean
}

export interface QuoteResponse {
  symbol: string
  timestamp: string
  last_price: number
  bid: number | null
  ask: number | null
  volume: number | null
  change: number | null
  change_percent: number | null
  open_price: number | null
  high_price: number | null
  low_price: number | null
}

export interface CurrentBarResponse {
  symbol: string
  interval: string
  bar_start: string
  bar_end: string | null
  open: number | null
  high: number | null
  low: number | null
  close: number | null
  volume: number
  tick_count: number
  is_in_progress?: boolean
  staleness_ms?: number | null
}

export interface CandlestickData {
  time: UTCTimestamp
  open: number
  high: number
  low: number
  close: number
}

export interface VolumeData {
  time: UTCTimestamp
  value: number
  color: string
}

export interface ChartData {
  candles: CandlestickData[]
  volumes: VolumeData[]
  lastBarRaw?: { id: string; datetime: string }
}

export interface SyncStatus {
  symbol: string
  interval: string
  status: string
  bar_count: number
  last_sync_at: string | null
  last_bar_at: string | null
  error_message: string | null
  consecutive_empty_fetches?: number
  is_stuck?: boolean
}

export interface IntegrityReport {
  symbol: string
  interval: string
  total: number
  misaligned_count: number
  misaligned_ids: string[]
  missing_count: number
  gap_ranges: [string, string][]
}

export interface RepairResult {
  symbol: string
  interval: string
  deleted: number
  gaps_resynced: number
  missing_before: number
  still_missing: number
  still_missing_ranges: [string, string][]
}

export interface JobLastRun {
  started_at: string
  finished_at: string | null
  duration_ms: number | null
  status: 'running' | 'completed' | 'failed' | 'missed' | 'skipped_max_instances'
  error: string | null
}

export interface JobInfo {
  id: string
  name: string
  next_run: string | null
  trigger: string
  last_run: JobLastRun | null
}

export type Interval = '1m' | '5m' | '15m' | '1h' | '4h' | '1d' | '1w'

export interface IndicatorConfig {
  sma: boolean
  ema: boolean
  rsi: boolean
  macd: boolean
  bollinger: boolean
}
