import type { UTCTimestamp } from 'lightweight-charts'
import type { OHLCVBar, ChartData } from '../types/market-data'

const VOLUME_UP = 'rgba(38, 166, 154, 0.3)'
const VOLUME_DOWN = 'rgba(239, 83, 80, 0.3)'

// DB stores UTC. Naive strings (no offset) are UTC, so append Z; strings with an offset
// or a trailing Z parse as-is.
export function toUTCTimestamp(iso: string): UTCTimestamp {
  const normalized = iso.includes('+') || iso.endsWith('Z') ? iso : iso + 'Z'
  const ms = new Date(normalized).getTime()
  if (Number.isNaN(ms)) throw new Error(`Invalid datetime: ${iso}`)
  return (ms / 1000) as UTCTimestamp
}

// Keyed by epoch seconds, not array index, so sliding-window refetches merge or overwrite
// without dropping older bars or duplicating the boundary bar.
export type BarMap = Map<number, OHLCVBar>

// Overwrites on time collision because a refetched bar may carry an updated final close.
// Returns the count of new keys; zero means no older bars exist.
export function mergeBars(map: BarMap, bars: OHLCVBar[]): number {
  let added = 0
  for (const bar of bars) {
    const t = toUTCTimestamp(bar.datetime)
    if (!map.has(t)) added++
    map.set(t, bar)
  }
  return added
}

export function barsToChartData(bars: OHLCVBar[]): ChartData {
  const sorted = [...bars].sort(
    (a, b) => toUTCTimestamp(a.datetime) - toUTCTimestamp(b.datetime),
  )
  const candles = sorted.map((bar) => ({
    time: toUTCTimestamp(bar.datetime),
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
  }))
  const volumes = sorted.map((bar) => ({
    time: toUTCTimestamp(bar.datetime),
    value: bar.volume,
    color: bar.close >= bar.open ? VOLUME_UP : VOLUME_DOWN,
  }))
  const lastBar = sorted.at(-1)
  const lastBarRaw = lastBar ? { id: lastBar.id, datetime: lastBar.datetime } : undefined
  return { candles, volumes, lastBarRaw }
}

export function accToChartData(map: BarMap): ChartData {
  return barsToChartData([...map.values()])
}

// Sent verbatim as the next page's end_date so the backend re-parses its own output (no
// tz/format drift). The $lte boundary re-returns this bar, which the merge dedupes.
export function earliestCursor(map: BarMap): string | undefined {
  let minTime = Infinity
  let cursor: string | undefined
  for (const [t, bar] of map) {
    if (t < minTime) {
      minTime = t
      cursor = bar.datetime
    }
  }
  return cursor
}
