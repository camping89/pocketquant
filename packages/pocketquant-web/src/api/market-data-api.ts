import type { UTCTimestamp } from 'lightweight-charts'
import { apiFetch } from './api-client'
import type {
  OHLCVResponse,
  SymbolInfo,
  SyncStatus,
  CurrentBarResponse,
  ChartData,
  Interval,
} from '../types/market-data'
import { encodeSymbolForUrl } from '../lib/symbol-format'

const VOLUME_UP = 'rgba(38, 166, 154, 0.3)'
const VOLUME_DOWN = 'rgba(239, 83, 80, 0.3)'

function toUTCTimestamp(iso: string): UTCTimestamp {
  // DB stores UTC. Naive strings (no offset) must be treated as UTC — append Z.
  // Strings with offset (+00:00) are parsed correctly as-is.
  const normalized = iso.includes('+') || iso.endsWith('Z') ? iso : iso + 'Z'
  const ms = new Date(normalized).getTime()
  if (Number.isNaN(ms)) throw new Error(`Invalid datetime: ${iso}`)
  return (ms / 1000) as UTCTimestamp
}

/** Fetch OHLCV bars for a composite symbol (e.g. "BTCUSDT:BINANCE"). */
export async function fetchOHLCV(
  symbol: string,
  interval: Interval,
  limit = 1000,
): Promise<ChartData> {
  const res = await apiFetch<OHLCVResponse>(
    `/api/v1/market-data/ohlcv/${encodeSymbolForUrl(symbol)}`,
    { interval, limit: String(limit) },
  )

  // API returns desc order; LC v5 requires ascending
  const bars = [...res.data].reverse()

  const candles = bars.map((bar) => ({
    time: toUTCTimestamp(bar.datetime),
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
  }))

  const volumes = bars.map((bar) => ({
    time: toUTCTimestamp(bar.datetime),
    value: bar.volume,
    color: bar.close >= bar.open ? VOLUME_UP : VOLUME_DOWN,
  }))

  const lastBar = bars.length > 0 ? bars[bars.length - 1] : undefined
  const lastBarRaw = lastBar ? { id: lastBar.id, datetime: lastBar.datetime } : undefined

  return { candles, volumes, lastBarRaw }
}

/** Fetch all active symbols as composite strings (e.g. ["BTCUSDT:BINANCE", ...]). */
export async function fetchSymbols(): Promise<SymbolInfo[]> {
  return apiFetch<SymbolInfo[]>('/api/v1/market-data/symbols')
}

/** Fetch the current in-progress bar for a composite symbol. */
export async function fetchCurrentBar(
  symbol: string,
  interval: Interval,
): Promise<CurrentBarResponse> {
  return apiFetch<CurrentBarResponse>(
    `/api/v1/quotes/current-bar/${encodeSymbolForUrl(symbol)}`,
    { interval },
  )
}

export async function fetchSyncStatus(): Promise<SyncStatus[]> {
  return apiFetch<SyncStatus[]>('/api/v1/market-data/sync-status')
}

export { toUTCTimestamp }
