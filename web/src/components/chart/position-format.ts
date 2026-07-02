/** Shared numeric formatters for the position box primitive + its info card. */

/** Quantity: strip scientific notation, max 8 significant digits, no trailing zeros. */
export function fmtQty(n: number): string {
  if (n === 0) return '0'
  if (!isFinite(n)) return String(n)
  return parseFloat(n.toPrecision(8)).toString()
}

/** Price with 2 decimals. */
export function fmtPrice(n: number): string {
  return n.toFixed(2)
}

/** PnL with explicit sign and 2 decimals. */
export function fmtPnl(n: number): string {
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}`
}

/** Fee: 4 significant digits, no trailing zeros. */
export function fmtFee(n: number): string {
  return parseFloat(n.toPrecision(4)).toString()
}
