// Realtime clock in the app-nav. Ticks every second; follows the tz dropdown.

import { useEffect, useState } from 'react'
import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import { useTimezone } from '../../lib/use-timezone'
import { tzSuffix } from '../../lib/datetime'

dayjs.extend(utc) // idempotent — also extended in datetime.ts

export function LiveClock() {
  const { mode } = useTimezone()
  const [now, setNow] = useState(() => dayjs())

  useEffect(() => {
    const id = setInterval(() => setNow(dayjs()), 1000)
    return () => clearInterval(id)
  }, [])

  const t = mode === 'utc' ? now.utc() : now.local()
  return (
    <span className="live-clock" title="Current time">
      {t.format('HH:mm:ss')} {tzSuffix(mode)}
    </span>
  )
}
