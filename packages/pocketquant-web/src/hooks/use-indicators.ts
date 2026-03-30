import { useMemo } from 'react'
import type { UTCTimestamp } from 'lightweight-charts'
import type { CandlestickData, IndicatorConfig } from '../types/market-data'
import { sma, ema } from '../lib/indicators/moving-average'
import { rsi as computeRSI } from '../lib/indicators/rsi'
import { macd as computeMACD } from '../lib/indicators/macd'
import { bollingerBands as computeBB } from '../lib/indicators/bollinger-bands'

export interface LinePoint {
  time: UTCTimestamp
  value: number
}

export interface IndicatorData {
  sma20: LinePoint[]
  ema50: LinePoint[]
  rsi14: LinePoint[]
  macdLine: LinePoint[]
  macdSignal: LinePoint[]
  macdHistogram: { time: UTCTimestamp; value: number; color: string }[]
  bbUpper: LinePoint[]
  bbMiddle: LinePoint[]
  bbLower: LinePoint[]
}

function toLinePoints(
  times: UTCTimestamp[],
  values: (number | null)[],
): LinePoint[] {
  const result: LinePoint[] = []
  for (let i = 0; i < values.length; i++) {
    if (values[i] !== null) {
      result.push({ time: times[i], value: values[i] as number })
    }
  }
  return result
}

export function useIndicators(
  candles: CandlestickData[] | undefined,
  config: IndicatorConfig,
): IndicatorData | null {
  return useMemo(() => {
    if (!candles || candles.length === 0) return null

    const closes = candles.map((c) => c.close)
    const times = candles.map((c) => c.time)

    const sma20 = config.sma ? toLinePoints(times, sma(closes, 20)) : []
    const ema50 = config.ema ? toLinePoints(times, ema(closes, 50)) : []
    const rsi14 = config.rsi ? toLinePoints(times, computeRSI(closes, 14)) : []

    let macdLine: LinePoint[] = []
    let macdSignal: LinePoint[] = []
    let macdHistogram: { time: UTCTimestamp; value: number; color: string }[] = []
    if (config.macd) {
      const m = computeMACD(closes)
      macdLine = toLinePoints(times, m.macdLine)
      macdSignal = toLinePoints(times, m.signalLine)
      macdHistogram = []
      for (let i = 0; i < m.histogram.length; i++) {
        if (m.histogram[i] !== null) {
          macdHistogram.push({
            time: times[i],
            value: m.histogram[i] as number,
            color: (m.histogram[i] as number) >= 0 ? '#66BB6A' : '#EF5350',
          })
        }
      }
    }

    let bbUpper: LinePoint[] = []
    let bbMiddle: LinePoint[] = []
    let bbLower: LinePoint[] = []
    if (config.bollinger) {
      const bb = computeBB(closes)
      bbUpper = toLinePoints(times, bb.upper)
      bbMiddle = toLinePoints(times, bb.middle)
      bbLower = toLinePoints(times, bb.lower)
    }

    return { sma20, ema50, rsi14, macdLine, macdSignal, macdHistogram, bbUpper, bbMiddle, bbLower }
  }, [candles, config])
}
