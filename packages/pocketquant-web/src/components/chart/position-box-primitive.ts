/**
 * Lightweight-charts v5 primitive that renders complete position visualizations:
 * background box, SL/TP dashed lines with price labels, entry price line, and info text.
 */

import type {
  CanvasRenderingTarget2D,
  IChartApiBase,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  Time,
} from 'lightweight-charts'

/** Format quantity: strip scientific notation, max 8 significant digits */
function fmtQty(n: number): string {
  if (n === 0) return '0'
  if (!isFinite(n)) return String(n)
  // Use toPrecision to get significant digits, then strip trailing zeros
  return parseFloat(n.toPrecision(8)).toString()
}

/** Format price with 2 decimals */
function fmtPrice(n: number): string {
  return n.toFixed(2)
}

/** Format PnL with sign and 2 decimals */
function fmtPnl(n: number): string {
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}`
}

/** Format fee — 4 sig digits, no trailing zeros */
function fmtFee(n: number): string {
  return parseFloat(n.toPrecision(4)).toString()
}

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
}

const FONT_SIZE = 9   // CSS px
const LINE_HEIGHT = 13 // CSS px
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
  constructor(
    private readonly positions: PositionData[],
    private readonly chart: IChartApiBase<Time>,
    private readonly series: ISeriesApi<'Candlestick', Time>,
  ) {}

  draw(_target: CanvasRenderingTarget2D): void {}

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

        // --- background box (sl → tp) ---
        if (ySL != null && yTP != null) {
          const boxTop = Math.min(ySL, yTP) * vR
          const boxH = Math.abs(ySL - yTP) * vR
          ctx.fillStyle = pos.pnl >= 0 ? 'rgba(38,166,154,0.09)' : 'rgba(239,83,80,0.09)'
          ctx.fillRect(lx, boxTop, boxW, boxH)
        }

        // --- TP line + label ---
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

        // --- SL line + label ---
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

        // --- entry price line ---
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

        // --- info text block (top-left of box) ---
        const boxTopY = ySL != null && yTP != null
          ? Math.min(ySL, yTP) * vR
          : (yEntry != null ? yEntry * vR : null)

        if (boxTopY != null) {
          const lines: { text: string; color: string }[] = [
            { text: `Entry ${fmtPrice(pos.entry_price)}`, color: '#90CAF9' },
          ]
          if (pos.exit_price != null) {
            lines.push({ text: `Exit  ${fmtPrice(pos.exit_price)}`, color: '#FFB74D' })
          }
          lines.push({ text: `Qty   ${fmtQty(pos.quantity)}`, color: '#B0BEC5' })
          lines.push({
            text: `PnL   ${fmtPnl(pos.pnl)}`,
            color: pos.pnl >= 0 ? '#26a69a' : '#ef5350',
          })
          lines.push({ text: `Fee   ${fmtFee(pos.commission)}`, color: '#90A4AE' })

          ctx.save()
          ctx.font = `${FONT_SIZE * vR}px monospace`
          let ty = boxTopY + (PAD + LINE_HEIGHT) * vR
          for (const line of lines) {
            ctx.fillStyle = line.color
            ctx.textAlign = 'left'
            ctx.textBaseline = 'top'
            ctx.fillText(line.text, lx + PAD * hR, ty)
            ty += LINE_HEIGHT * vR
          }
          ctx.restore()
        }
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

export class PositionBoxPrimitive implements ISeriesPrimitive<Time> {
  private _positions: PositionData[]
  private _view: BoxPaneView | null = null

  constructor(positions: PositionData[]) {
    this._positions = positions
  }

  attached(param: SeriesAttachedParameter<Time, 'Candlestick'>): void {
    this._view = new BoxPaneView(
      this._positions,
      param.chart as IChartApiBase<Time>,
      param.series,
    )
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this._view ? [this._view] : []
  }
}
