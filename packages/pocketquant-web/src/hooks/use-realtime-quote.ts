import { useEffect, useRef, useState } from 'react'
import type { QuoteStreamPayload } from '../types/quote'

export interface RealtimeQuoteState {
  quote: QuoteStreamPayload | null
  isStale: boolean
  lastUpdateTs: number | null
}

// Stale after 10s with no SSE event
const STALE_THRESHOLD_MS = 10_000
// How often we re-evaluate staleness
const STALE_CHECK_INTERVAL_MS = 2_000

// REST fallback: fetch initial quote to avoid blank first render
async function fetchInitialQuote(
  exchange: string,
  symbol: string,
): Promise<QuoteStreamPayload | null> {
  try {
    const res = await fetch(new URL(
      `/api/v1/quotes/latest/${exchange}/${symbol}`,
      window.location.origin,
    ))
    if (!res.ok) return null
    const data = await res.json() as {
      symbol: string
      exchange: string
      last_price: number
      bid: number | null
      ask: number | null
      volume: number | null
      change: number | null
      change_percent: number | null
      timestamp: string
    }
    // Map REST field `timestamp` → SSE field `ts`
    return {
      symbol: data.symbol,
      exchange: data.exchange,
      last_price: data.last_price,
      bid: data.bid,
      ask: data.ask,
      volume: data.volume,
      change: data.change,
      change_percent: data.change_percent,
      ts: data.timestamp,
    }
  } catch {
    return null
  }
}

export function useRealtimeQuote(exchange: string, symbol: string): RealtimeQuoteState {
  const [quote, setQuote] = useState<QuoteStreamPayload | null>(null)
  const [lastUpdateTs, setLastUpdateTs] = useState<number | null>(null)
  const [isStale, setIsStale] = useState(false)

  // Refs are safe to read/write inside effects and callbacks — never during render
  const lastPriceRef = useRef<number | null>(null)
  const lastVolumeRef = useRef<number | null>(null)
  const lastUpdateTsRef = useRef<number | null>(null)

  useEffect(() => {
    // Reset tracking state inside the effect (not during render)
    lastPriceRef.current = null
    lastVolumeRef.current = null
    lastUpdateTsRef.current = null

    let cancelled = false

    // Kick off initial REST fetch so the widget populates before the first SSE event
    fetchInitialQuote(exchange, symbol).then((initial) => {
      if (cancelled || initial === null) return
      const now = Date.now()
      lastPriceRef.current = initial.last_price
      lastVolumeRef.current = initial.volume
      lastUpdateTsRef.current = now
      setQuote(initial)
      setLastUpdateTs(now)
    })

    const url = `/api/v1/quotes/stream/${exchange}/${symbol}`
    const es = new EventSource(url)

    es.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data as string) as QuoteStreamPayload

        // Skip redundant renders — only update on meaningful change
        const priceChanged = payload.last_price !== lastPriceRef.current
        const volumeChanged = payload.volume !== lastVolumeRef.current
        if (!priceChanged && !volumeChanged) return

        lastPriceRef.current = payload.last_price
        lastVolumeRef.current = payload.volume
        const now = Date.now()
        lastUpdateTsRef.current = now
        setQuote(payload)
        setLastUpdateTs(now)
        setIsStale(false)
      } catch {
        // malformed SSE event — ignore
      }
    }

    // Periodically re-evaluate staleness so indicator updates without waiting for SSE
    const staleTimer = setInterval(() => {
      const ts = lastUpdateTsRef.current
      if (ts !== null) {
        setIsStale(Date.now() - ts > STALE_THRESHOLD_MS)
      }
    }, STALE_CHECK_INTERVAL_MS)

    return () => {
      cancelled = true
      es.close()
      clearInterval(staleTimer)
    }
  }, [exchange, symbol])

  return { quote, isStale, lastUpdateTs }
}
