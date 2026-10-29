// Composite symbol format: "{CODE}:{EXCHANGE}" (e.g. "BTCUSDT:BINANCE", "XAUUSD:EXNESS").
// Decompose only at the display layer, never in business logic.

export function parseSymbol(composite: string): { code: string; exchange: string } {
  const idx = composite.indexOf(':')
  if (idx === -1) return { code: composite, exchange: '' }
  return { code: composite.slice(0, idx), exchange: composite.slice(idx + 1) }
}

export function encodeSymbolForUrl(composite: string): string {
  return encodeURIComponent(composite)
}
