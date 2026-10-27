import { apiFetch } from './api-client'
import type {
  OHLCVResponse,
  DataLag,
  SymbolInfo,
  SyncStatus,
  OHLCVBar,
  Interval,
} from '../types/market-data'
import { encodeSymbolForUrl } from '../lib/symbol-format'
import { toUTCTimestamp } from '../lib/chart-history'

/** Fetch raw OHLCV bars (desc order, as the API returns them) for a composite
 * symbol. ``endDate`` (ISO string) caps the window to bars at/older than it —
 * the cursor for scroll-left pagination. */
export async function fetchOHLCVBars(
  symbol: string,
  interval: Interval,
  limit = 1000,
  endDate?: string,
): Promise<OHLCVBar[]> {
  const params: Record<string, string> = { limit: String(limit) }
  if (endDate) params.end_date = endDate
  const res = await apiFetch<OHLCVResponse>(
    `/api/v1/market-data/ohlcv/${encodeSymbolForUrl(symbol)}/${interval}`,
    params,
  )
  return res.data
}

/** Fetch all active symbols as composite strings (e.g. ["BTCUSDT:BINANCE", ...]). */
export async function fetchSymbols(): Promise<SymbolInfo[]> {
  return apiFetch<SymbolInfo[]>('/api/v1/market-data/symbols')
}

export async function fetchSyncStatus(): Promise<SyncStatus[]> {
  return apiFetch<SyncStatus[]>('/api/v1/market-data/sync-status')
}

export async function fetchDataLag(symbol: string): Promise<DataLag> {
  return apiFetch<DataLag>(`/api/v1/market-data/data-lag/${encodeSymbolForUrl(symbol)}`)
}

export { toUTCTimestamp }
