import { INTERVAL_MS } from './datetime'

// The order only keeps the chips readable; the backend owns the interval rule and its 422 message reaches the user.
export function sortIntervals(list: readonly string[]): string[] {
  return [...list].sort((a, b) => INTERVAL_MS[a] - INTERVAL_MS[b])
}

export function configLabel(
  intervals: readonly string[] | undefined,
  fallback: string | undefined,
  parameters: Record<string, unknown> | undefined,
): string {
  const ivs = (intervals ?? (fallback ? [fallback] : [])).join(' ')
  const params = parameters ?? {}
  const keys = Object.keys(params).sort()
  if (keys.length === 0) return ivs
  return `${ivs} · ${keys.map((k) => `${k}=${String(params[k])}`).join(' ')}`
}
