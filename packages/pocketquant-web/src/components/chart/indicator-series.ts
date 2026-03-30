import {
  LineSeries,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  type SeriesType,
} from 'lightweight-charts'
import type { IndicatorData } from '../../hooks/use-indicators'
import type { IndicatorConfig } from '../../types/market-data'

const COLORS = {
  sma20: '#2196F3',
  ema50: '#FF9800',
  rsi: '#AB47BC',
  macdLine: '#26C6DA',
  macdSignal: '#FF7043',
  bbUpper: 'rgba(33, 150, 243, 0.4)',
  bbMiddle: '#2196F3',
  bbLower: 'rgba(33, 150, 243, 0.4)',
}

export interface IndicatorSeriesRefs {
  all: ISeriesApi<SeriesType>[]
}

export function addIndicatorSeries(
  chart: IChartApi,
  data: IndicatorData,
  config: IndicatorConfig,
): IndicatorSeriesRefs {
  const all: ISeriesApi<SeriesType>[] = []

  // Overlay indicators on pane 0
  if (config.sma && data.sma20.length > 0) {
    const s = chart.addSeries(LineSeries, { color: COLORS.sma20, lineWidth: 1, priceScaleId: 'right' })
    s.setData(data.sma20)
    all.push(s)
  }

  if (config.ema && data.ema50.length > 0) {
    const s = chart.addSeries(LineSeries, { color: COLORS.ema50, lineWidth: 1, priceScaleId: 'right' })
    s.setData(data.ema50)
    all.push(s)
  }

  if (config.bollinger) {
    if (data.bbUpper.length > 0) {
      const s = chart.addSeries(LineSeries, { color: COLORS.bbUpper, lineWidth: 1, priceScaleId: 'right' })
      s.setData(data.bbUpper)
      all.push(s)
    }
    if (data.bbMiddle.length > 0) {
      const s = chart.addSeries(LineSeries, { color: COLORS.bbMiddle, lineWidth: 1, priceScaleId: 'right', lineStyle: 2 })
      s.setData(data.bbMiddle)
      all.push(s)
    }
    if (data.bbLower.length > 0) {
      const s = chart.addSeries(LineSeries, { color: COLORS.bbLower, lineWidth: 1, priceScaleId: 'right' })
      s.setData(data.bbLower)
      all.push(s)
    }
  }

  // Track next available pane index for sub-chart indicators
  let nextPane = 1

  // RSI in separate pane
  if (config.rsi && data.rsi14.length > 0) {
    const s = chart.addSeries(LineSeries, { color: COLORS.rsi, lineWidth: 1 }, nextPane)
    s.setData(data.rsi14)
    all.push(s)
    nextPane++
  }

  // MACD in next separate pane
  if (config.macd) {
    const pane = nextPane
    if (data.macdLine.length > 0) {
      const s = chart.addSeries(LineSeries, { color: COLORS.macdLine, lineWidth: 1 }, pane)
      s.setData(data.macdLine)
      all.push(s)
    }
    if (data.macdSignal.length > 0) {
      const s = chart.addSeries(LineSeries, { color: COLORS.macdSignal, lineWidth: 1 }, pane)
      s.setData(data.macdSignal)
      all.push(s)
    }
    if (data.macdHistogram.length > 0) {
      const s = chart.addSeries(HistogramSeries, {}, pane)
      s.setData(data.macdHistogram)
      all.push(s)
    }
  }

  return { all }
}

export function removeIndicatorSeries(
  chart: IChartApi,
  refs: IndicatorSeriesRefs,
): void {
  for (const s of refs.all) {
    try { chart.removeSeries(s) } catch { /* chart already disposed */ }
  }
}
