import type { UTCTimestamp } from 'lightweight-charts'
import type { OHLCVBar, ChartData } from '../types/market-data'

const VOLUME_UP = 'rgba(38, 166, 154, 0.3)'
const VOLUME_DOWN = 'rgba(239, 83, 80, 0.3)'

/** DB stores UTC. Naive strings (no offset) must be treated as UTC — append Z.
 * Strings with offset (+00:00) or trailing Z are parsed as-is. */
export function toUTCTimestamp(iso: string): UTCTimestamp {
  const normalized = iso.includes('+') || iso.endsWith('Z') ? iso : iso + 'Z'
  const ms = new Date(normalized).getTime()
  if (Number.isNaN(ms)) throw new Error(`Invalid datetime: ${iso}`)
  return (ms / 1000) as UTCTimestamp
}

/** Map keyed by epoch-seconds — the accumulator backing pagination. Keying by
 * time (not array index) lets sliding-window refetches merge/overwrite without
 * dropping older bars or duplicating the boundary bar. */
export type BarMap = Map<number, OHLCVBar>

/** Merge bars into the accumulator, overwriting on time collision (a refetched
 * bar may carry an updated final close). Returns how many keys were newly
 * added — zero means the page contributed no history, the terminal signal for
 * "no older bars exist". */
export function mergeBars(map: BarMap, bars: OHLCVBar[]): number {
  let added = 0
  for (const bar of bars) {
    const t = toUTCTimestamp(bar.datetime)
    if (!map.has(t)) added++
    map.set(t, bar)
  }
  return added
}

/** Build the lightweight-charts dataset from a flat bar list (any order). */
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

/** Ascending-sorted chart dataset built from the accumulator. */
export function accToChartData(map: BarMap): ChartData {
  return barsToChartData([...map.values()])
}

/** Raw datetime string of the earliest accumulated bar — sent verbatim as the
 * next page's ``end_date`` so the backend re-parses its own output (no tz/format
 * drift). The ``$lte`` boundary re-returns this bar, which merge dedupes. */
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
