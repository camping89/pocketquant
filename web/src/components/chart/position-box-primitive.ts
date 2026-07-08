/**
 * Lightweight-charts v5 primitive that renders position ZONES onto the chart in two
 * stacked layers:
 *   - Fill layer (zOrder 'bottom', drawBackground) — behind the candles: an ambient
 *     soft zone per trade (fill + faint entry line) plus a stronger shaded SL↔TP zone
 *     for the selected / hovered trade.
 *   - Level-line layer (zOrder 'top', draw) — above the candles: dashed entry/exit/
 *     SL/TP lines for the active detail box only, each CLAMPED to the trade's box
 *     span (not full-width). Their on-axis price labels are owned by TradingChart
 *     (createPriceLine with lineVisible:false, axisLabelVisible:true) so the label
 *     reaches the price axis while the line stays inside the box.
 * Numeric stats render in the HTML OHLCV legend.
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
  /** Ambient (always-on) preview drawn for every trade so its zone is visible
   *  without clicking: a soft blurred fill + faint entry line, no SL/TP lines,
   *  no outline, no info card. Detail boxes (click/hover) draw over it. */
  ambient?: boolean
}

// On-axis label colors for the active trade's levels — kept in sync with the
// createPriceLine titles in TradingChart so the box-bounded line matches its
// axis label hue.
const LEVEL_COLORS = {
  entry: '#90CAF9',
  exit: '#FFB74D',
  sl: '#ef5350',
  tp: '#26a69a',
} as const

// Project a position's [x1, x2] span to canvas x-pixels, clamped to the canvas
// and to the visible time window. Returns null when the box is off-screen or
// collapses to zero width. Shared by the zone-fill and level-line renderers.
function projectSpan(
  pos: PositionData,
  timeScale: ReturnType<IChartApiBase<Time>['timeScale']>,
  hR: number,
  width: number,
  vFrom: number | null,
  vTo: number | null,
): { lx: number; rx: number; boxW: number } | null {
  if (vFrom != null && vTo != null && typeof pos.x1 === 'number' && typeof pos.x2 === 'number') {
    if (Math.max(pos.x1, pos.x2) < vFrom || Math.min(pos.x1, pos.x2) > vTo) return null
  }
  const cx1 = timeScale.timeToCoordinate(pos.x1)
  const cx2 = timeScale.timeToCoordinate(pos.x2)
  if (cx1 == null || cx2 == null) return null
  const lx = Math.max(Math.min(cx1, cx2) * hR, 0)
  const rx = Math.min(Math.max(cx1, cx2) * hR, width)
  const boxW = rx - lx
  if (boxW <= 0) return null
  return { lx, rx, boxW }
}

// Zone fills — the 'bottom' layer, behind the candles (drawBackground).
class FillRenderer implements IPrimitivePaneRenderer {
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

  draw(): void {}

  drawBackground(target: CanvasRenderingTarget2D): void {
    target.useBitmapCoordinateSpace(({ context: ctx, horizontalPixelRatio: hR, verticalPixelRatio: vR, bitmapSize }) => {
      const timeScale = this.chart.timeScale()
      const width = bitmapSize.width

      // A full-history run can hold tens of thousands of trades. Projecting and
      // filling every one each frame — on every pan / zoom / crosshair move — melts
      // the chart. Cull to the visible time window first with a plain numeric
      // compare (~free); only boxes overlapping the viewport pay for coordinate
      // projection + fill.
      const vr = timeScale.getVisibleRange()
      const vFrom = typeof vr?.from === 'number' ? vr.from : null
      const vTo = typeof vr?.to === 'number' ? vr.to : null

      for (const pos of this.positions) {
        const span = projectSpan(pos, timeScale, hR, width, vFrom, vTo)
        if (!span) continue
        const { lx, rx, boxW } = span

        const ySL = pos.sl_price != null ? this.series.priceToCoordinate(pos.sl_price) : null
        const yTP = pos.tp_price != null ? this.series.priceToCoordinate(pos.tp_price) : null
        const yEntry = this.series.priceToCoordinate(pos.entry_price)

        // Ambient preview: soft flat zone fill + faint entry line only. Colored by
        // realized PnL so winners/losers read at a glance across the whole run. No
        // shadow blur here — it is per-box, per-frame, and murderous at scale.
        if (pos.ambient) {
          const win = pos.pnl >= 0
          if (ySL != null && yTP != null) {
            const boxTop = Math.min(ySL, yTP) * vR
            const boxH = Math.abs(ySL - yTP) * vR
            ctx.fillStyle = win ? 'rgba(38,166,154,0.07)' : 'rgba(239,83,80,0.07)'
            ctx.fillRect(lx, boxTop, boxW, boxH)
          }
          if (yEntry != null) {
            const y = yEntry * vR
            ctx.save()
            ctx.strokeStyle = win ? 'rgba(38,166,154,0.35)' : 'rgba(239,83,80,0.35)'
            ctx.lineWidth = vR
            ctx.beginPath()
            ctx.moveTo(lx, y)
            ctx.lineTo(rx, y)
            ctx.stroke()
            ctx.restore()
          }
          continue
        }

        // Selected / hovered trade: a stronger SL↔TP zone fill only. The entry/TP/
        // SL/exit levels themselves are drawn as box-bounded lines by LineRenderer
        // (on top of the candles), with on-axis labels owned by TradingChart. Color
        // by realized PnL (closed) or direction (open).
        if (ySL != null && yTP != null) {
          const boxTop = Math.min(ySL, yTP) * vR
          const boxH = Math.abs(ySL - yTP) * vR
          const isOpen = pos.exit_price == null
          const dir = pos.direction ?? 'LONG'
          const win = isOpen ? dir === 'LONG' : pos.pnl >= 0
          const alpha = pos.highlightKind ? 0.24 : isOpen ? 0.06 : 0.09
          ctx.fillStyle = win ? `rgba(38,166,154,${alpha})` : `rgba(239,83,80,${alpha})`
          ctx.fillRect(lx, boxTop, boxW, boxH)
        }
      }
    })
  }
}

// Level lines (entry/exit/SL/TP) for the active detail box — the 'top' layer, ON
// TOP of the candles (draw()), each clamped to the box span. The matching on-axis
// labels are owned by TradingChart's price lines (lineVisible:false, label-only).
class LineRenderer implements IPrimitivePaneRenderer {
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
      const width = bitmapSize.width
      const vr = timeScale.getVisibleRange()
      const vFrom = typeof vr?.from === 'number' ? vr.from : null
      const vTo = typeof vr?.to === 'number' ? vr.to : null

      for (const pos of this.positions) {
        // Only the detail (clicked/hovered) box shows level lines — ambient boxes
        // keep just their faint entry line drawn in the fill layer.
        if (!pos.highlightKind) continue

        const span = projectSpan(pos, timeScale, hR, width, vFrom, vTo)
        if (!span) continue
        const { lx, rx } = span

        const line = (price: number | null, color: string) => {
          if (price == null) return
          const yc = this.series.priceToCoordinate(price)
          if (yc == null) return
          const y = yc * vR
          ctx.save()
          ctx.strokeStyle = color
          ctx.lineWidth = vR
          ctx.setLineDash([4 * hR, 4 * hR])
          ctx.beginPath()
          ctx.moveTo(lx, y)
          ctx.lineTo(rx, y)
          ctx.stroke()
          ctx.restore()
        }

        line(pos.entry_price, LEVEL_COLORS.entry)
        line(pos.exit_price, LEVEL_COLORS.exit)
        line(pos.sl_price, LEVEL_COLORS.sl)
        line(pos.tp_price, LEVEL_COLORS.tp)
      }
    })
  }
}

class FillPaneView implements IPrimitivePaneView {
  private _renderer: FillRenderer

  constructor(
    positions: PositionData[],
    chart: IChartApiBase<Time>,
    series: ISeriesApi<'Candlestick', Time>,
  ) {
    this._renderer = new FillRenderer(positions, chart, series)
  }

  zOrder() {
    return 'bottom' as const
  }

  renderer() {
    return this._renderer
  }
}

class LinePaneView implements IPrimitivePaneView {
  private _renderer: LineRenderer

  constructor(
    positions: PositionData[],
    chart: IChartApiBase<Time>,
    series: ISeriesApi<'Candlestick', Time>,
  ) {
    this._renderer = new LineRenderer(positions, chart, series)
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
      new FillPaneView(this._positions, chart, param.series),
      new LinePaneView(this._positions, chart, param.series),
    ]
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this._views
  }
}
