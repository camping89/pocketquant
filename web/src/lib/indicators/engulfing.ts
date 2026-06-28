import type { SeriesMarker, Time } from 'lightweight-charts'
import type { CandlestickData } from '../../types/market-data'

// Mirror of the Python detector in
// src/pocketquant/core/domain/strategy/patterns/engulfing_detector.py.
// Locked to it by the shared golden fixture (engulfing.test.ts).

const NO_SIGNAL_REJECTION = 1.0

export interface EngulfingResult {
  isBullish: boolean
  isBearish: boolean
  rejectionWickPct: number
}

interface OHLC {
  open: number
  high: number
  low: number
  close: number
}

export function detectEngulfing(prev: OHLC, curr: OHLC): EngulfingResult {
  const isBullish =
    prev.close < prev.open &&
    curr.close > curr.open &&
    curr.open <= prev.close &&
    curr.close >= prev.open
  const isBearish =
    prev.close > prev.open &&
    curr.close < curr.open &&
    curr.open >= prev.close &&
    curr.close <= prev.open

  if (!isBullish && !isBearish) {
    return { isBullish: false, isBearish: false, rejectionWickPct: NO_SIGNAL_REJECTION }
  }

  const range = curr.high - curr.low
  let rejectionWickPct: number
  if (range === 0) {
    rejectionWickPct = NO_SIGNAL_REJECTION
  } else if (isBullish) {
    rejectionWickPct = (curr.high - curr.close) / range
  } else {
    rejectionWickPct = (curr.close - curr.low) / range
  }

  return { isBullish, isBearish, rejectionWickPct }
}

const COLORS = {
  bullishStrong: '#16a34a',
  bullishWeak: '#86efac',
  bearishStrong: '#dc2626',
  bearishWeak: '#fca5a5',
} as const

// Visual aid only: a fixed display threshold for strong/weak coloring. The
// backtest reads max_rejection_wick_pct from config and may differ — see
// docs/swing-pivot-key-level.md.
export const STRONG_THRESHOLD = 0.3

export function engulfingMarkers(
  candles: CandlestickData[],
  threshold: number = STRONG_THRESHOLD,
): SeriesMarker<Time>[] {
  const markers: SeriesMarker<Time>[] = []
  for (let i = 1; i < candles.length; i++) {
    const res = detectEngulfing(candles[i - 1], candles[i])
    if (!res.isBullish && !res.isBearish) continue
    const strong = res.rejectionWickPct <= threshold
    if (res.isBullish) {
      markers.push({
        time: candles[i].time as Time,
        position: 'belowBar',
        color: strong ? COLORS.bullishStrong : COLORS.bullishWeak,
        shape: 'arrowUp',
        text: 'Engulf',
      })
    } else {
      markers.push({
        time: candles[i].time as Time,
        position: 'aboveBar',
        color: strong ? COLORS.bearishStrong : COLORS.bearishWeak,
        shape: 'arrowDown',
        text: 'Engulf',
      })
    }
  }
  return markers
}
