import { describe, it, expect } from 'vitest'
import {
  mergeBars,
  accToChartData,
  earliestCursor,
  toUTCTimestamp,
  type BarMap,
} from './chart-history'
import type { OHLCVBar } from '../types/market-data'

function bar(datetime: string, close = 100): OHLCVBar {
  return { id: datetime, datetime, open: 100, high: 101, low: 99, close, volume: 10 }
}

describe('mergeBars', () => {
  it('counts only net-new keys', () => {
    const m: BarMap = new Map()
    expect(mergeBars(m, [bar('2026-06-29T10:00:00'), bar('2026-06-29T10:01:00')])).toBe(2)
    expect(mergeBars(m, [bar('2026-06-29T10:01:00'), bar('2026-06-29T10:02:00')])).toBe(1)
  })

  it('overwrites on time collision (refreshed final close)', () => {
    const m: BarMap = new Map()
    mergeBars(m, [bar('2026-06-29T10:00:00', 100)])
    mergeBars(m, [bar('2026-06-29T10:00:00', 105)])
    expect(m.size).toBe(1)
    expect([...m.values()][0].close).toBe(105)
  })

  it('boundary-only page (cursor re-returned) yields added<=1 → terminal signal', () => {
    const m: BarMap = new Map()
    mergeBars(m, [bar('2026-06-29T10:00:00'), bar('2026-06-29T10:01:00')])
    // simulate older-page fetch with end_date=earliest: $lte re-returns only the cursor
    const added = mergeBars(m, [bar('2026-06-29T10:00:00')])
    expect(added).toBe(0)
  })
})

describe('accToChartData', () => {
  it('returns ascending candles regardless of insert order', () => {
    const m: BarMap = new Map()
    mergeBars(m, [
      bar('2026-06-29T10:02:00'),
      bar('2026-06-29T10:00:00'),
      bar('2026-06-29T10:01:00'),
    ])
    const cd = accToChartData(m)
    const times = cd.candles.map((c) => c.time as number)
    expect(times).toEqual([...times].sort((a, b) => a - b))
    expect(cd.candles).toHaveLength(3)
    expect(cd.volumes).toHaveLength(3)
  })

  it('lastBarRaw points at the latest bar', () => {
    const m: BarMap = new Map()
    mergeBars(m, [bar('2026-06-29T10:00:00'), bar('2026-06-29T10:05:00')])
    expect(accToChartData(m).lastBarRaw?.datetime).toBe('2026-06-29T10:05:00')
  })
})

describe('earliestCursor', () => {
  it('returns the raw datetime string of the earliest bar', () => {
    const m: BarMap = new Map()
    mergeBars(m, [bar('2026-06-29T10:05:00'), bar('2026-06-29T10:00:00')])
    expect(earliestCursor(m)).toBe('2026-06-29T10:00:00')
  })

  it('undefined on empty accumulator', () => {
    expect(earliestCursor(new Map())).toBeUndefined()
  })
})

describe('toUTCTimestamp', () => {
  it('treats naive strings as UTC', () => {
    expect(toUTCTimestamp('2026-06-29T00:00:00')).toBe(
      toUTCTimestamp('2026-06-29T00:00:00Z'),
    )
  })

  it('throws on invalid input', () => {
    expect(() => toUTCTimestamp('not-a-date')).toThrow()
  })
})
