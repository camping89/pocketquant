const PLACEHOLDER = '—'

const priceFmt = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

/** Price: 2 decimals + thousands separator, en-US fixed so `,` is stable
 *  regardless of browser locale. `109169.14140000001` → `109,169.14`. */
export function formatPrice(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return PLACEHOLDER
  return priceFmt.format(n)
}

/** Quantity: significant-digits view that keeps magnitude for tiny crypto sizes
 *  while shedding float noise. `toPrecision(8)` then `Number(...)` drops the
 *  trailing zeros + `…0001` tail; large integers pass through unchanged. */
export function formatQty(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return PLACEHOLDER
  if (n === 0) return '0'
  return String(Number(n.toPrecision(8)))
}

/** USD amount: `$` + 2 decimals + thousands separator, sign only when negative.
 *  For unsigned money (notional, fee): `$103.75`, `-$1.20`. */
export function formatUsd(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return PLACEHOLDER
  return `${n < 0 ? '-' : ''}$${priceFmt.format(Math.abs(n))}`
}

/** USD amount with explicit sign — for PnL / net where direction matters:
 *  `+$0.08`, `-$0.13`. */
export function formatUsdSigned(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return PLACEHOLDER
  return `${n < 0 ? '-' : '+'}$${priceFmt.format(Math.abs(n))}`
}

const feeFmt = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
})

/** USD fee: keeps up to 4 decimals for small per-trade fees where 2 dp rounds
 *  away meaningful precision. `0.2076` → `$0.2076`, `0.21` → `$0.21`. */
export function formatUsdPrecise(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return PLACEHOLDER
  return `${n < 0 ? '-' : ''}$${feeFmt.format(Math.abs(n))}`
}
