import { useDataLag } from '../hooks/use-data-lag'
import { dataLagLabel, dataLagMessage } from '../lib/data-lag'
import { parseSymbol } from '../lib/symbol-format'

interface DataLagBadgeProps {
  /** Composite symbol string: "{CODE}:{EXCHANGE}" e.g. "ES1!:CME_MINI" */
  symbol: string
}

/** Shown only while the symbol's data runs behind real time; hover explains why. */
export function DataLagBadge({ symbol }: DataLagBadgeProps) {
  const { data } = useDataLag(symbol)
  if (!data) return null
  const label = dataLagLabel(data.state, data.lag_seconds)
  if (!label) return null
  const message = dataLagMessage(parseSymbol(symbol).code, data.state, data.lag_seconds)
  return (
    <span
      className={`data-lag-badge data-lag-badge--${data.state}`}
      role="status"
      title={message ?? undefined}
      aria-label={message ?? label}
    >
      {label}
    </span>
  )
}
