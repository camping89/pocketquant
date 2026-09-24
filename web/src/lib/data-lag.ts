// Wording for the data-lag flag. The API returns state + seconds; the text
// lives here so every surface (ticker, monitor) says the same thing.

import type { FeedState } from '../types/market-data'

/** "12 min", "1 h 5 min" — lag is whole minutes, so seconds are dropped. */
export function formatLag(seconds: number): string {
  const minutes = Math.max(1, Math.round(seconds / 60))
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest ? `${hours} h ${rest} min` : `${hours} h`
}

/** Short badge text, or null when there is nothing to flag. */
export function dataLagLabel(state: FeedState, lagSeconds: number | null): string | null {
  if (lagSeconds === null) return null
  if (state === 'delayed') return `Delayed ~${formatLag(lagSeconds)}`
  if (state === 'stuck') return `Stalled ~${formatLag(lagSeconds)}`
  return null
}

/** The explanation shown on hover, or null when the data is current. */
export function dataLagMessage(
  code: string,
  state: FeedState,
  lagSeconds: number | null,
): string | null {
  if (lagSeconds === null) return null
  const lag = formatLag(lagSeconds)
  if (state === 'delayed') {
    return (
      `${code} data is about ${lag} behind real time. The data provider's feed is ` +
      `delayed, so prices and bars keep updating, just late. Nothing needs fixing.`
    )
  }
  if (state === 'stuck') {
    return (
      `${code} data is about ${lag} behind real time and has stopped catching up: ` +
      `no new bar has arrived for several minutes. The feed may have stalled, or the ` +
      `market is unusually quiet. It recovers on its own when bars resume.`
    )
  }
  return null
}
