// React context for tz mode preference. Provider only — hooks live in `use-timezone.ts`
// (split so fast-refresh works: react-refresh requires component-only files).

import { createContext, useCallback, useMemo, useState, type ReactNode } from 'react'
import { type TimezoneMode, tzSuffix } from './datetime'

const STORAGE_KEY = 'pq.tz.mode'

function readInitialMode(): TimezoneMode {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw === 'local' ? 'local' : 'utc'
  } catch {
    return 'utc'
  }
}

export interface TimezoneContextValue {
  mode: TimezoneMode
  setMode: (m: TimezoneMode) => void
  suffix: string
}

// eslint-disable-next-line react-refresh/only-export-components
export const TimezoneContext = createContext<TimezoneContextValue | null>(null)

export function TimezoneProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<TimezoneMode>(readInitialMode)

  const setMode = useCallback((m: TimezoneMode) => {
    try { localStorage.setItem(STORAGE_KEY, m) } catch { /* swallow */ }
    setModeState(m)
  }, [])

  const suffix = useMemo(() => tzSuffix(mode), [mode])
  const value = useMemo(() => ({ mode, setMode, suffix }), [mode, setMode, suffix])

  return <TimezoneContext.Provider value={value}>{children}</TimezoneContext.Provider>
}
