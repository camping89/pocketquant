export function fmtQty(n: number): string {
  if (n === 0) return '0'
  if (!isFinite(n)) return String(n)
  return parseFloat(n.toPrecision(8)).toString()
}

// 2 decimals for >= 1000 (indices, BTC), 3 for >= 10 (JPY pairs), 5 below (FX majors such as EURUSD).
export function fmtPrice(n: number): string {
  const abs = Math.abs(n)
  return n.toFixed(abs >= 1000 ? 2 : abs >= 10 ? 3 : 5)
}

export function fmtPnl(n: number): string {
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}`
}

export function fmtFee(n: number): string {
  return parseFloat(n.toPrecision(4)).toString()
}
