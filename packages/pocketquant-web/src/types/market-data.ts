import type { UTCTimestamp } from 'lightweight-charts'

// --- API response types ---

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
  exchange: string
  interval: string
  data: OHLCVBar[]
  count: number
}

export interface SymbolInfo {
  symbol: string
  exchange: string
  name: string
  asset_type: string
  is_active: boolean
}

export interface QuoteResponse {
  symbol: string
  exchange: string
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
  exchange: string
  interval: string
  bar_start: string
  bar_end: string | null
  open: number | null
  high: number | null
  low: number | null
  close: number | null
  volume: number
  tick_count: number
}

// --- Lightweight Charts data types ---

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
  exchange: string
  interval: string
  status: string
  bar_count: number
  last_sync_at: string | null
  last_bar_at: string | null
  error_message: string | null
}

// --- Monitor types ---

export interface IntegrityReport {
  symbol: string
  exchange: string
  interval: string
  total: number
  misaligned_count: number
  misaligned_ids: string[]
  missing_count: number
  gap_ranges: [string, string][]
}

export interface RepairResult {
  symbol: string
  exchange: string
  interval: string
  deleted: number
  gaps_resynced: number
  missing_before: number
}

export interface JobInfo {
  id: string
  next_run: string | null
  trigger: string
}

// --- UI types ---

export type Interval = '1m' | '3m' | '5m' | '15m' | '30m' | '45m' | '1h' | '2h' | '3h' | '4h' | '1d' | '1w' | '1M'

export interface IndicatorConfig {
  sma: boolean
  ema: boolean
  rsi: boolean
  macd: boolean
  bollinger: boolean
}

export interface SelectedSymbol {
  exchange: string
  symbol: string
}
