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

export async function fetchOHLCV(
  exchange: string,
  symbol: string,
  interval: Interval,
  limit = 1000,
): Promise<ChartData> {
  const res = await apiFetch<OHLCVResponse>(
    `/api/v1/market-data/ohlcv/${exchange}/${symbol}`,
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

export async function fetchSymbols(exchange?: string): Promise<SymbolInfo[]> {
  const params: Record<string, string> = {}
  if (exchange) params.exchange = exchange
  return apiFetch<SymbolInfo[]>('/api/v1/market-data/symbols', params)
}

export async function fetchCurrentBar(
  exchange: string,
  symbol: string,
  interval: Interval,
): Promise<CurrentBarResponse> {
  return apiFetch<CurrentBarResponse>(
    `/api/v1/quotes/current-bar/${exchange}/${symbol}`,
    { interval },
  )
}

export async function fetchSyncStatus(): Promise<SyncStatus[]> {
  return apiFetch<SyncStatus[]>('/api/v1/market-data/sync-status')
}

export { toUTCTimestamp }
