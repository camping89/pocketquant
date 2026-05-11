import type { BacktestPosition } from '../../../api/backtest-api'

export type FilterKey = 'all' | 'wins' | 'losses' | 'open'

export type SortKey =
  | 'index'
  | 'entry_time'
  | 'direction'
  | 'entry_price'
  | 'exit_price'
  | 'quantity'
  | 'duration'
  | 'pnl'
  | 'commission'
  | 'status'

export type SortDir = 'asc' | 'desc'

export interface IndexedPosition {
  index: number // original index in backtest.positions
  position: BacktestPosition
}

export function applyFilter(positions: IndexedPosition[], filter: FilterKey): IndexedPosition[] {
  switch (filter) {
    case 'wins':
      return positions.filter((p) => (p.position.pnl ?? 0) > 0)
    case 'losses':
      return positions.filter((p) => (p.position.pnl ?? 0) < 0)
    case 'open':
      return positions.filter((p) => p.position.exit_time == null)
    case 'all':
    default:
      return positions
  }
}

function durationSeconds(p: BacktestPosition): number {
  if (!p.exit_time) return Number.POSITIVE_INFINITY
  return (new Date(p.exit_time).getTime() - new Date(p.entry_time).getTime()) / 1000
}

function valueFor(p: BacktestPosition, key: SortKey, fallbackIndex: number): number | string {
  switch (key) {
    case 'index': return fallbackIndex
    case 'entry_time': return new Date(p.entry_time).getTime()
    case 'direction': return p.direction ?? 'LONG'
    case 'entry_price': return p.entry_price
    case 'exit_price': return p.exit_price ?? Number.NEGATIVE_INFINITY
    case 'quantity': return p.quantity
    case 'duration': return durationSeconds(p)
    case 'pnl': return p.pnl
    case 'commission': return p.commission
    case 'status': return p.exit_time ? 'closed' : 'open'
  }
}

export function sortPositions(
  positions: IndexedPosition[],
  key: SortKey,
  dir: SortDir,
): IndexedPosition[] {
  const mul = dir === 'asc' ? 1 : -1
  return [...positions].sort((a, b) => {
    const av = valueFor(a.position, key, a.index)
    const bv = valueFor(b.position, key, b.index)
    if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * mul
    return String(av).localeCompare(String(bv)) * mul
  })
}

export function fmtDuration(p: BacktestPosition): string {
  if (!p.exit_time) return '—'
  const sec = durationSeconds(p)
  if (sec < 60) return `${Math.round(sec)}s`
  if (sec < 3600) return `${Math.round(sec / 60)}m`
  if (sec < 86400) {
    const h = Math.floor(sec / 3600)
    const m = Math.floor((sec % 3600) / 60)
    return `${h}h ${m}m`
  }
  const d = Math.floor(sec / 86400)
  const h = Math.floor((sec % 86400) / 3600)
  return `${d}d ${h}h`
}

export function fmtPnl(n: number): string {
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}`
}

export function fmtPrice(n: number | null): string {
  if (n == null) return '—'
  return n.toFixed(2)
}

export function fmtDateTime(s: string): string {
  const d = new Date(s)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`
}

export function aggregatePnl(positions: IndexedPosition[]): number {
  return positions.reduce((sum, p) => sum + (p.position.pnl ?? 0), 0)
}
