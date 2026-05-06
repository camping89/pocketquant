// Stateless dot indicating SSE freshness: green = live, yellow = warn (>10s), red = stale (>30s)

interface TickerStaleIndicatorProps {
  lastUpdateTs: number | null
}

const WARN_THRESHOLD_MS = 10_000
const STALE_THRESHOLD_MS = 30_000

function getColor(lastUpdateTs: number | null): string {
  if (lastUpdateTs === null) return '#8b8b9a' // grey — no data yet
  const age = Date.now() - lastUpdateTs
  if (age > STALE_THRESHOLD_MS) return '#ef5350' // red
  if (age > WARN_THRESHOLD_MS) return '#ffa726'  // yellow/orange
  return '#26a69a'                                // green
}

export function TickerStaleIndicator({ lastUpdateTs }: TickerStaleIndicatorProps) {
  const color = getColor(lastUpdateTs)
  return (
    <span
      title={lastUpdateTs === null ? 'No data' : `Last update: ${new Date(lastUpdateTs).toLocaleTimeString()}`}
      style={{
        display: 'inline-block',
        width: 8,
        height: 8,
        borderRadius: '50%',
        backgroundColor: color,
        flexShrink: 0,
      }}
    />
  )
}
