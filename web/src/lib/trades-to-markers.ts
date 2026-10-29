import { type SeriesMarker, type UTCTimestamp } from 'lightweight-charts'
import type { Trade } from '../types/strategy'

function toUTC(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp
}

export function tradesToMarkers(trades: Trade[]): SeriesMarker<UTCTimestamp>[] {
  return trades
    .map((t): SeriesMarker<UTCTimestamp> => {
      const time = toUTC(t.timestamp)

      if (!t.is_entry) {
        // Exit marker — neutral slate square above bar
        return {
          time,
          position: 'aboveBar',
          color: '#94a3b8',
          shape: 'square',
          text: 'X',
        }
      }

      if (t.side === 'long') {
        return {
          time,
          position: 'belowBar',
          color: '#10b981',
          shape: 'arrowUp',
          text: `L+${t.qty}`,
        }
      }

      // short entry
      return {
        time,
        position: 'aboveBar',
        color: '#f43f5e',
        shape: 'arrowDown',
        text: `S-${t.qty}`,
      }
    })
    .sort((a, b) => (a.time as number) - (b.time as number))
}
