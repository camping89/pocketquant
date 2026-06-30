import { describe, it, expect } from 'vitest'
import {
  histogram,
  computeStreaks,
  profitFactorByDirection,
  topDrawdowns,
} from './stats-utils'
import type { BacktestPosition, EquityPoint } from '../../api/backtest-api'

function pos(p: Partial<BacktestPosition>): BacktestPosition {
  return {
    direction: 'LONG',
    entry_price: 100,
    entry_time: '2026-01-01T00:00:00',
    exit_price: 110,
    exit_time: '2026-01-01T01:00:00',
    quantity: 1,
    sl_price: null,
    tp_price: null,
    pnl: 0,
    commission: 0,
    ...p,
  }
}

function eq(timestamp: string, equity: number, drawdown: number): EquityPoint {
  return { timestamp, equity, drawdown }
}

describe('histogram', () => {
  it('returns [] for empty input', () => {
    expect(histogram([])).toEqual([])
  })

  it('collapses equal values to a single bin', () => {
    const bins = histogram([5, 5, 5])
    expect(bins).toHaveLength(1)
    expect(bins[0].count).toBe(3)
  })

  it('keeps the max value in the last bin (half-open clamp)', () => {
    const bins = histogram([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 5)
    const total = bins.reduce((a, b) => a + b.count, 0)
    expect(total).toBe(11) // no value dropped
    expect(bins[bins.length - 1].count).toBeGreaterThanOrEqual(1) // 10 landed
  })
})

describe('computeStreaks', () => {
  it('tracks longest win and loss runs, ignoring open and break-even', () => {
    const positions = [
      pos({ pnl: 5 }),
      pos({ pnl: 3 }),
      pos({ pnl: -2 }),
      pos({ pnl: -1 }),
      pos({ pnl: -4 }),
      pos({ pnl: 0 }), // break-even resets
      pos({ pnl: 2 }),
      pos({ exit_time: null, pnl: 99 }), // open, ignored
    ]
    expect(computeStreaks(positions)).toEqual({ maxWinStreak: 2, maxLossStreak: 3 })
  })
})

describe('profitFactorByDirection', () => {
  it('splits gross profit / gross loss per direction; null when no loss', () => {
    const positions = [
      pos({ direction: 'LONG', pnl: 100 }),
      pos({ direction: 'LONG', pnl: -50 }),
      pos({ direction: 'SHORT', pnl: 30 }), // no SHORT loss → null
    ]
    const pf = profitFactorByDirection(positions)
    expect(pf.long).toBeCloseTo(2.0)
    expect(pf.short).toBeNull()
  })
})

describe('topDrawdowns', () => {
  it('detects a recovered drawdown with start, trough, recovery', () => {
    const curve = [
      eq('2026-01-01T00:00:00', 100, 0),
      eq('2026-01-01T01:00:00', 90, -0.1),
      eq('2026-01-01T02:00:00', 80, -0.2), // trough
      eq('2026-01-01T03:00:00', 100, 0), // recovery
    ]
    const [dd] = topDrawdowns(curve, 5)
    expect(dd.depth).toBeCloseTo(-0.2)
    expect(dd.startTime).toBe('2026-01-01T01:00:00')
    expect(dd.troughTime).toBe('2026-01-01T02:00:00')
    expect(dd.recoveryTime).toBe('2026-01-01T03:00:00')
  })

  it('marks an unrecovered tail drawdown with null recovery', () => {
    const curve = [
      eq('2026-01-01T00:00:00', 100, 0),
      eq('2026-01-01T01:00:00', 80, -0.2),
    ]
    const [dd] = topDrawdowns(curve, 5)
    expect(dd.recoveryTime).toBeNull()
  })

  it('returns deepest first, capped at topN', () => {
    const curve = [
      eq('t0', 100, 0),
      eq('t1', 95, -0.05),
      eq('t2', 100, 0),
      eq('t3', 70, -0.3),
      eq('t4', 100, 0),
    ]
    const periods = topDrawdowns(curve, 1)
    expect(periods).toHaveLength(1)
    expect(periods[0].depth).toBeCloseTo(-0.3)
  })
})
