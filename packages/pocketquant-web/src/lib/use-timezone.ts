// Hooks for consuming TimezoneContext. Split from `timezone-context.tsx` to keep
// that file component-only (required by react-refresh ESLint rule).

import { useContext, useMemo } from 'react'
import { TimezoneContext, type TimezoneContextValue } from './timezone-context'
import {
  formatBarDate,
  formatHmsTime,
  formatNextRun,
  formatFullDateTime,
  formatDateTime,
} from './datetime'

export function useTimezone(): TimezoneContextValue {
  const ctx = useContext(TimezoneContext)
  if (!ctx) throw new Error('useTimezone must be used inside <TimezoneProvider>')
  return ctx
}

/** Mode-bound formatters. Closures recompute when `mode` changes. */
export function useFmt() {
  const { mode, suffix } = useTimezone()
  return useMemo(() => ({
    mode,
    suffix,
    barDate: (iso: string | null | undefined) => formatBarDate(iso, mode),
    hmsTime: (iso: string | null | undefined) => formatHmsTime(iso, mode),
    nextRun: (iso: string | null | undefined) => formatNextRun(iso, mode),
    fullDateTime: (iso: string | null | undefined) => formatFullDateTime(iso, mode),
    /** Format with arbitrary dayjs format string (e.g. 'HH:mm'). */
    format: (iso: string | null | undefined, fmt: string) => formatDateTime(iso, mode, fmt),
  }), [mode, suffix])
}
