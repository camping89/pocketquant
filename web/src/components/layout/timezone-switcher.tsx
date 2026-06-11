// Header dropdown for switching display tz mode (UTC / Local).
// Self-contained via context — adds no props to the parent header.

import { useTimezone } from '../../lib/use-timezone'
import { tzSuffix, type TimezoneMode } from '../../lib/datetime'

export function TimezoneSwitcher() {
  const { mode, setMode } = useTimezone()
  const localLabel = `Local (${tzSuffix('local')})`

  return (
    <select
      className="strategy-select"
      value={mode}
      onChange={(e) => setMode(e.target.value as TimezoneMode)}
      title="Display timezone"
      aria-label="Display timezone"
    >
      <option value="utc">UTC</option>
      <option value="local">{localLabel}</option>
    </select>
  )
}
