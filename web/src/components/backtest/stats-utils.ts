import type { BacktestPosition, EquityPoint } from '../../api/backtest-api'

/** A single histogram bucket: [lo, hi) range and the count falling inside it. */
export interface HistogramBin {
  lo: number
  hi: number
  count: number
}

/** Bucket values into ``binCount`` equal-width bins spanning [min, max].
 *  Empty input → []. A degenerate range (all equal) collapses to one bin. */
export function histogram(values: number[], binCount = 20): HistogramBin[] {
  if (values.length === 0) return []
  const min = Math.min(...values)
  const max = Math.max(...values)
  if (min === max) return [{ lo: min, hi: max, count: values.length }]

  const width = (max - min) / binCount
  const bins: HistogramBin[] = Array.from({ length: binCount }, (_, i) => ({
    lo: min + i * width,
    hi: min + (i + 1) * width,
    count: 0,
  }))
  for (const v of values) {
    // Clamp the top edge into the last bin so max isn't dropped by the half-open range.
    const idx = Math.min(binCount - 1, Math.floor((v - min) / width))
    bins[idx].count += 1
  }
  return bins
}

export interface StreakStats {
  maxWinStreak: number
  maxLossStreak: number
}

/** Longest consecutive run of wins / losses over closed positions in order.
 *  Open positions (exit_time null) and break-even (pnl === 0) reset the streak. */
export function computeStreaks(positions: BacktestPosition[]): StreakStats {
  let maxWin = 0
  let maxLoss = 0
  let curWin = 0
  let curLoss = 0
  for (const p of positions) {
    if (p.exit_time == null) continue
    if (p.pnl > 0) {
      curWin += 1
      curLoss = 0
      maxWin = Math.max(maxWin, curWin)
    } else if (p.pnl < 0) {
      curLoss += 1
      curWin = 0
      maxLoss = Math.max(maxLoss, curLoss)
    } else {
      curWin = 0
      curLoss = 0
    }
  }
  return { maxWinStreak: maxWin, maxLossStreak: maxLoss }
}

export interface DirectionProfitFactor {
  long: number | null
  short: number | null
}

/** Profit factor (gross profit / gross loss) split by direction.
 *  null when a direction has no losing PnL (factor undefined / infinite). The
 *  aggregate profit factor is NOT recomputed here — read it from BE metrics. */
export function profitFactorByDirection(positions: BacktestPosition[]): DirectionProfitFactor {
  const acc = { LONG: { profit: 0, loss: 0 }, SHORT: { profit: 0, loss: 0 } }
  for (const p of positions) {
    if (p.exit_time == null) continue
    const side = acc[p.direction]
    if (p.pnl >= 0) side.profit += p.pnl
    else side.loss += Math.abs(p.pnl)
  }
  const factor = (s: { profit: number; loss: number }) => (s.loss > 0 ? s.profit / s.loss : null)
  return { long: factor(acc.LONG), short: factor(acc.SHORT) }
}

export interface DrawdownPeriod {
  /** Peak-to-trough depth as a negative fraction (e.g. -0.18 = −18%). */
  depth: number
  startTime: string
  troughTime: string
  /** Timestamp equity first reclaimed the prior peak, or null if still under water. */
  recoveryTime: string | null
  durationSeconds: number
}

/** Top-N drawdown periods scanned from the equity curve's per-point drawdown.
 *
 *  A period opens when drawdown goes negative, tracks its deepest point, and
 *  closes when equity reclaims the prior peak (drawdown returns to ~0). Recovery
 *  is the first point back at the peak; an unrecovered tail period has
 *  ``recoveryTime: null``. Returned sorted by depth (deepest first). */
export function topDrawdowns(curve: EquityPoint[], topN = 5): DrawdownPeriod[] {
  const periods: DrawdownPeriod[] = []
  let open: { startTime: string; troughTime: string; depth: number } | null = null

  const epochSeconds = (iso: string) => new Date(iso).getTime() / 1000

  for (const pt of curve) {
    if (pt.drawdown < 0) {
      if (open == null) {
        open = { startTime: pt.timestamp, troughTime: pt.timestamp, depth: pt.drawdown }
      } else if (pt.drawdown < open.depth) {
        open.depth = pt.drawdown
        open.troughTime = pt.timestamp
      }
    } else if (open != null) {
      periods.push({
        depth: open.depth,
        startTime: open.startTime,
        troughTime: open.troughTime,
        recoveryTime: pt.timestamp,
        durationSeconds: epochSeconds(pt.timestamp) - epochSeconds(open.startTime),
      })
      open = null
    }
  }
  // Tail drawdown that never recovered before the curve ended.
  if (open != null) {
    const last = curve[curve.length - 1]
    periods.push({
      depth: open.depth,
      startTime: open.startTime,
      troughTime: open.troughTime,
      recoveryTime: null,
      durationSeconds: epochSeconds(last.timestamp) - epochSeconds(open.startTime),
    })
  }

  return periods.sort((a, b) => a.depth - b.depth).slice(0, topN)
}
