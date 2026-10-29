const PLACEHOLDER = '—'

const priceFmt = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

// en-US is fixed so the thousands separator is stable regardless of browser locale.
export function formatPrice(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return PLACEHOLDER
  return priceFmt.format(n)
}

// toPrecision(8) then Number(...) keeps magnitude for tiny crypto sizes while dropping
// trailing zeros and the float-noise tail; large integers pass through unchanged.
export function formatQty(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return PLACEHOLDER
  if (n === 0) return '0'
  return String(Number(n.toPrecision(8)))
}

export function formatUsd(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return PLACEHOLDER
  return `${n < 0 ? '-' : ''}$${priceFmt.format(Math.abs(n))}`
}

export function formatUsdSigned(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return PLACEHOLDER
  return `${n < 0 ? '-' : '+'}$${priceFmt.format(Math.abs(n))}`
}

const feeFmt = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
})

// Up to 4 decimals: for small per-trade fees, 2 dp rounds away meaningful precision.
export function formatUsdPrecise(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return PLACEHOLDER
  return `${n < 0 ? '-' : ''}$${feeFmt.format(Math.abs(n))}`
}
