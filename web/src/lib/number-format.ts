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
