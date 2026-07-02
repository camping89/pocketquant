/**
 * Renders the position box's stats as a legible two-column card on a solid
 * background panel — labels left (muted), values right (colored) — instead of
 * bare text drawn over candles/lines where it overlaps into an unreadable mess.
 */

import type { PositionData } from './position-box-primitive'
import { fmtFee, fmtPnl, fmtPrice, fmtQty } from './position-format'

const FONT_SIZE = 9    // CSS px
const LINE_HEIGHT = 14 // CSS px
const PAD_X = 6        // CSS px
const PAD_Y = 5        // CSS px
const COL_GAP = 12     // CSS px between label and value columns
const INSET = 3        // CSS px offset from the box corner

interface Bounds {
  width: number
  height: number
}

interface Anchor {
  left: number
  top: number
}

interface StatRow {
  label: string
  value: string
  color: string
}

function buildRows(pos: PositionData): StatRow[] {
  const rows: StatRow[] = [{ label: 'Entry', value: fmtPrice(pos.entry_price), color: '#90CAF9' }]
  if (pos.exit_price != null) rows.push({ label: 'Exit', value: fmtPrice(pos.exit_price), color: '#FFB74D' })
  rows.push({ label: 'Qty', value: fmtQty(pos.quantity), color: '#CFD8DC' })
  rows.push({ label: 'PnL', value: fmtPnl(pos.pnl), color: pos.pnl >= 0 ? '#26a69a' : '#ef5350' })
  rows.push({ label: 'Fee', value: fmtFee(pos.commission), color: '#90A4AE' })
  return rows
}

/**
 * All incoming coordinates/bounds are in bitmap (device) pixels; hR/vR scale
 * CSS-px constants into that space so the card stays crisp at any DPR.
 */
export function drawPositionInfoCard(
  ctx: CanvasRenderingContext2D,
  hR: number,
  vR: number,
  bounds: Bounds,
  anchor: Anchor,
  pos: PositionData,
): void {
  const dir = pos.direction ?? 'LONG'
  const dirColor = dir === 'LONG' ? '#26a69a' : '#ef5350'
  const header = `[${dir}]`
  const rows = buildRows(pos)

  ctx.save()
  ctx.font = `${FONT_SIZE * vR}px monospace`
  ctx.textBaseline = 'top'

  let labelW = 0
  let valueW = 0
  for (const r of rows) {
    labelW = Math.max(labelW, ctx.measureText(r.label).width)
    valueW = Math.max(valueW, ctx.measureText(r.value).width)
  }
  const innerW = Math.max(ctx.measureText(header).width, labelW + COL_GAP * hR + valueW)
  const cardW = innerW + 2 * PAD_X * hR
  const cardH = (rows.length + 1) * LINE_HEIGHT * vR + 2 * PAD_Y * vR

  // Anchor at the box's top-left, then clamp inside the visible canvas so the
  // card never spills past an edge when the box sits near the chart border.
  let x = anchor.left + INSET * hR
  let y = anchor.top + INSET * vR
  if (x + cardW > bounds.width) x = bounds.width - cardW - INSET * hR
  if (y + cardH > bounds.height) y = bounds.height - cardH - INSET * vR
  if (x < INSET * hR) x = INSET * hR
  if (y < INSET * vR) y = INSET * vR

  const radius = 4 * Math.min(hR, vR)
  ctx.beginPath()
  if (typeof ctx.roundRect === 'function') ctx.roundRect(x, y, cardW, cardH, radius)
  else ctx.rect(x, y, cardW, cardH)
  ctx.fillStyle = 'rgba(17,19,23,0.9)'
  ctx.fill()
  ctx.lineWidth = vR
  ctx.strokeStyle = dir === 'LONG' ? 'rgba(38,166,154,0.7)' : 'rgba(239,83,80,0.7)'
  ctx.stroke()

  const labelX = x + PAD_X * hR
  const valueX = x + cardW - PAD_X * hR
  let ty = y + PAD_Y * vR

  ctx.textAlign = 'left'
  ctx.fillStyle = dirColor
  ctx.fillText(header, labelX, ty)
  ty += LINE_HEIGHT * vR

  for (const r of rows) {
    ctx.textAlign = 'left'
    ctx.fillStyle = 'rgba(176,190,197,0.7)'
    ctx.fillText(r.label, labelX, ty)
    ctx.textAlign = 'right'
    ctx.fillStyle = r.color
    ctx.fillText(r.value, valueX, ty)
    ty += LINE_HEIGHT * vR
  }
  ctx.restore()
}
