/**
 * Lightweight-charts v5 primitive that renders complete position visualizations:
 * background box, SL/TP dashed lines with price labels, entry price line, and info text.
 */

import type {
  IChartApiBase,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  Time,
} from 'lightweight-charts'
import type { CanvasRenderingTarget2D } from 'fancy-canvas'
import { fmtPrice } from './position-format'
import { drawPositionInfoCard } from './position-box-info-card'

export interface PositionData {
  x1: Time
  x2: Time
  entry_price: number
  exit_price: number | null
  sl_price: number | null
  tp_price: number | null
  quantity: number
  pnl: number
  commission: number
  direction?: 'LONG' | 'SHORT'
  /** Which selection drew this box — solid outline for a click, dashed for a
   *  hover. Decoupled from any array index so paging can't misalign the outline. */
  highlightKind?: 'click' | 'hover'
}

const FONT_SIZE = 9   // CSS px
const PAD = 3         // CSS px

function dashedLine(
  ctx: CanvasRenderingContext2D,
  x1: number, y: number, x2: number,
  color: string, hR: number, vR: number,
) {
  ctx.save()
  ctx.strokeStyle = color
  ctx.lineWidth = vR
  ctx.setLineDash([4 * hR, 3 * hR])
  ctx.beginPath()
  ctx.moveTo(x1, y)
  ctx.lineTo(x2, y)
  ctx.stroke()
  ctx.restore()
}

class BoxRenderer implements IPrimitivePaneRenderer {
  private readonly positions: PositionData[]
  private readonly chart: IChartApiBase<Time>
  private readonly series: ISeriesApi<'Candlestick', Time>

  constructor(
    positions: PositionData[],
    chart: IChartApiBase<Time>,
    series: ISeriesApi<'Candlestick', Time>,
  ) {
    this.positions = positions
    this.chart = chart
    this.series = series
  }

  draw(target: CanvasRenderingTarget2D): void {
    void target
  }

  drawBackground(target: CanvasRenderingTarget2D): void {
    target.useBitmapCoordinateSpace(({ context: ctx, horizontalPixelRatio: hR, verticalPixelRatio: vR }) => {
      const timeScale = this.chart.timeScale()

      for (const pos of this.positions) {
        const cx1 = timeScale.timeToCoordinate(pos.x1)
        const cx2 = timeScale.timeToCoordinate(pos.x2)
        if (cx1 == null || cx2 == null) continue

        const lx = Math.min(cx1, cx2) * hR
        const rx = Math.max(cx1, cx2) * hR
        const boxW = rx - lx

        const ySL = pos.sl_price != null ? this.series.priceToCoordinate(pos.sl_price) : null
        const yTP = pos.tp_price != null ? this.series.priceToCoordinate(pos.tp_price) : null
        const yEntry = this.series.priceToCoordinate(pos.entry_price)

        if (ySL != null && yTP != null) {
          const boxTop = Math.min(ySL, yTP) * vR
          const boxH = Math.abs(ySL - yTP) * vR
          // Color by realized PnL (closed positions); open positions tinted by direction
          const isOpen = pos.exit_price == null
          const dir = pos.direction ?? 'LONG'
          if (isOpen) {
            ctx.fillStyle = dir === 'LONG' ? 'rgba(38,166,154,0.06)' : 'rgba(239,83,80,0.06)'
          } else {
            ctx.fillStyle = pos.pnl >= 0 ? 'rgba(38,166,154,0.09)' : 'rgba(239,83,80,0.09)'
          }
          ctx.fillRect(lx, boxTop, boxW, boxH)

          // Highlight outline (solid for click selection, dashed for hover)
          if (pos.highlightKind) {
            ctx.save()
            ctx.strokeStyle = '#FFD600'
            ctx.lineWidth = 2 * vR
            if (pos.highlightKind === 'hover') ctx.setLineDash([5 * hR, 4 * hR])
            ctx.strokeRect(lx, boxTop, boxW, boxH)
            ctx.restore()
          }
        }

        if (pos.tp_price != null && yTP != null) {
          const y = yTP * vR
          dashedLine(ctx, lx, y, rx, '#26a69a', hR, vR)
          ctx.save()
          ctx.font = `${FONT_SIZE * vR}px monospace`
          ctx.fillStyle = '#26a69a'
          ctx.textAlign = 'right'
          ctx.textBaseline = 'bottom'
          ctx.fillText(`TP ${fmtPrice(pos.tp_price)}`, rx - PAD * hR, y - PAD * vR)
          ctx.restore()
        }

        if (pos.sl_price != null && ySL != null) {
          const y = ySL * vR
          dashedLine(ctx, lx, y, rx, '#ef5350', hR, vR)
          ctx.save()
          ctx.font = `${FONT_SIZE * vR}px monospace`
          ctx.fillStyle = '#ef5350'
          ctx.textAlign = 'right'
          ctx.textBaseline = 'top'
          ctx.fillText(`SL ${fmtPrice(pos.sl_price)}`, rx - PAD * hR, y + PAD * vR)
          ctx.restore()
        }

        if (yEntry != null) {
          const y = yEntry * vR
          ctx.save()
          ctx.strokeStyle = 'rgba(144,202,249,0.6)'
          ctx.lineWidth = vR
          ctx.setLineDash([2 * hR, 2 * hR])
          ctx.beginPath()
          ctx.moveTo(lx, y)
          ctx.lineTo(rx, y)
          ctx.stroke()
          ctx.restore()
        }

      }
    })
  }
}

/**
 * Info cards draw in a separate top-layer pane view so they sit ABOVE the
 * candles — a card at the box's zOrder would be sliced by every candle drawn
 * over the trade region. Box left + top are recomputed here per frame.
 */
class CardRenderer implements IPrimitivePaneRenderer {
  private readonly positions: PositionData[]
  private readonly chart: IChartApiBase<Time>
  private readonly series: ISeriesApi<'Candlestick', Time>

  constructor(
    positions: PositionData[],
    chart: IChartApiBase<Time>,
    series: ISeriesApi<'Candlestick', Time>,
  ) {
    this.positions = positions
    this.chart = chart
    this.series = series
  }

  draw(target: CanvasRenderingTarget2D): void {
    target.useBitmapCoordinateSpace(({ context: ctx, horizontalPixelRatio: hR, verticalPixelRatio: vR, bitmapSize }) => {
      const timeScale = this.chart.timeScale()

      for (const pos of this.positions) {
        const cx1 = timeScale.timeToCoordinate(pos.x1)
        const cx2 = timeScale.timeToCoordinate(pos.x2)
        if (cx1 == null || cx2 == null) continue

        const ySL = pos.sl_price != null ? this.series.priceToCoordinate(pos.sl_price) : null
        const yTP = pos.tp_price != null ? this.series.priceToCoordinate(pos.tp_price) : null
        const yEntry = this.series.priceToCoordinate(pos.entry_price)
        const top = ySL != null && yTP != null
          ? Math.min(ySL, yTP) * vR
          : (yEntry != null ? yEntry * vR : null)
        if (top == null) continue

        drawPositionInfoCard(ctx, hR, vR, bitmapSize, { left: Math.min(cx1, cx2) * hR, top }, pos)
      }
    })
  }
}

class BoxPaneView implements IPrimitivePaneView {
  private _renderer: BoxRenderer

  constructor(
    positions: PositionData[],
    chart: IChartApiBase<Time>,
    series: ISeriesApi<'Candlestick', Time>,
  ) {
    this._renderer = new BoxRenderer(positions, chart, series)
  }

  zOrder() {
    return 'bottom' as const
  }

  renderer() {
    return this._renderer
  }
}

class CardPaneView implements IPrimitivePaneView {
  private _renderer: CardRenderer

  constructor(
    positions: PositionData[],
    chart: IChartApiBase<Time>,
    series: ISeriesApi<'Candlestick', Time>,
  ) {
    this._renderer = new CardRenderer(positions, chart, series)
  }

  zOrder() {
    return 'top' as const
  }

  renderer() {
    return this._renderer
  }
}

export class PositionBoxPrimitive implements ISeriesPrimitive<Time> {
  private _positions: PositionData[]
  private _views: IPrimitivePaneView[] = []

  constructor(positions: PositionData[]) {
    this._positions = positions
  }

  attached(param: SeriesAttachedParameter<Time, 'Candlestick'>): void {
    const chart = param.chart as IChartApiBase<Time>
    this._views = [
      new BoxPaneView(this._positions, chart, param.series),
      new CardPaneView(this._positions, chart, param.series),
    ]
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this._views
  }
}
