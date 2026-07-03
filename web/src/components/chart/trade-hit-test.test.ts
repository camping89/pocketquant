import { describe, it, expect } from 'vitest'
import { pickTradeAtTime, tradeMarkerToRow } from './trade-hit-test'
import type { TradeMarker } from '../../api/backtest-api'

const sec = (iso: string) => new Date(iso + 'Z').getTime() / 1000

function marker(over: Partial<TradeMarker>): TradeMarker {
  return {
    trade_id: 't',
    entry_time: '2024-01-01T00:00:00',
    exit_time: '2024-01-01T02:00:00',
    direction: 'LONG',
    entry_price: 100,
    exit_price: 110,
    sl_price: 95,
    tp_price: 115,
    quantity: 1,
    pnl: 10,
    commission: 0.5,
    ...over,
  }
}

describe('pickTradeAtTime', () => {
  const a = marker({ trade_id: 'a', entry_time: '2024-01-01T00:00:00', exit_time: '2024-01-01T02:00:00' })
  const b = marker({ trade_id: 'b', entry_time: '2024-01-01T05:00:00', exit_time: '2024-01-01T06:00:00' })

  it('returns the trade whose span contains the click', () => {
    expect(pickTradeAtTime([a, b], sec('2024-01-01T01:00:00'), 100, null)?.trade_id).toBe('a')
    expect(pickTradeAtTime([a, b], sec('2024-01-01T05:30:00'), 100, null)?.trade_id).toBe('b')
  })

  it('returns null when the click is outside every span (deselect)', () => {
    expect(pickTradeAtTime([a, b], sec('2024-01-01T03:00:00'), 100, null)).toBeNull()
  })

  it('includes the span boundaries', () => {
    expect(pickTradeAtTime([a], sec('2024-01-01T00:00:00'), null, null)?.trade_id).toBe('a')
    expect(pickTradeAtTime([a], sec('2024-01-01T02:00:00'), null, null)?.trade_id).toBe('a')
  })

  it('disambiguates overlapping spans by nearest entry price', () => {
    const lo = marker({ trade_id: 'lo', entry_price: 100, entry_time: '2024-01-01T00:00:00', exit_time: '2024-01-01T04:00:00' })
    const hi = marker({ trade_id: 'hi', entry_price: 200, entry_time: '2024-01-01T00:00:00', exit_time: '2024-01-01T04:00:00' })
    const t = sec('2024-01-01T02:00:00')
    expect(pickTradeAtTime([lo, hi], t, 190, null)?.trade_id).toBe('hi')
    expect(pickTradeAtTime([lo, hi], t, 105, null)?.trade_id).toBe('lo')
  })

  it('spans open trades (no exit_time) to lastCandleTime', () => {
    const open = marker({ trade_id: 'open', exit_time: null, entry_time: '2024-01-01T00:00:00' })
    const last = sec('2024-01-01T10:00:00')
    expect(pickTradeAtTime([open], sec('2024-01-01T08:00:00'), null, last)?.trade_id).toBe('open')
    expect(pickTradeAtTime([open], sec('2024-01-01T08:00:00'), null, null)).toBeNull()
  })
})

describe('tradeMarkerToRow', () => {
  it('derives duration_seconds from the span', () => {
    const row = tradeMarkerToRow(marker({ entry_time: '2024-01-01T00:00:00', exit_time: '2024-01-01T02:00:00' }))
    expect(row.duration_seconds).toBe(7200)
  })

  it('uses zero duration for open trades', () => {
    expect(tradeMarkerToRow(marker({ exit_time: null })).duration_seconds).toBe(0)
  })
})
