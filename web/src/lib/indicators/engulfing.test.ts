import { detectEngulfing } from './engulfing'
import fixture from './__fixtures__/engulfing_golden_fixture.json'

// Same fixture as the Python detector test. A byte-identical copy is diffed in
// Phase 5 to guard against TS/Python drift.

interface OHLC {
  open: number
  high: number
  low: number
  close: number
}
interface Case {
  name: string
  prev: OHLC
  curr: OHLC
  expected: { is_bullish: boolean; is_bearish: boolean; rejection_wick_pct: number }
}

const cases = (fixture as { cases: Case[] }).cases

describe('detectEngulfing golden-fixture parity', () => {
  for (const c of cases) {
    it(c.name, () => {
      const res = detectEngulfing(c.prev, c.curr)
      expect(res.isBullish).toBe(c.expected.is_bullish)
      expect(res.isBearish).toBe(c.expected.is_bearish)
      expect(res.rejectionWickPct).toBeCloseTo(c.expected.rejection_wick_pct, 12)
    })
  }
})
