// React context for UI theme (dark / light). Provider only — hook lives in
// `use-theme.ts` (split so fast-refresh works: react-refresh requires
// component-only files). Mirrors `timezone-context.tsx`.

import { createContext, useCallback, useMemo, useState, type ReactNode } from 'react'

export type ThemeMode = 'dark' | 'light'

const STORAGE_KEY = 'pq.theme.mode'

function applyAttribute(m: ThemeMode) {
  document.documentElement.setAttribute('data-theme', m)
}

function readInitialMode(): ThemeMode {
  let mode: ThemeMode = 'dark'
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw === 'light') mode = 'light'
  } catch { /* swallow */ }
  applyAttribute(mode)
  return mode
}

export interface ThemeContextValue {
  mode: ThemeMode
  setMode: (m: ThemeMode) => void
  toggle: () => void
}

// eslint-disable-next-line react-refresh/only-export-components
export const ThemeContext = createContext<ThemeContextValue | null>(null)

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(readInitialMode)

  const setMode = useCallback((m: ThemeMode) => {
    try { localStorage.setItem(STORAGE_KEY, m) } catch { /* swallow */ }
    applyAttribute(m)
    setModeState(m)
  }, [])

  const toggle = useCallback(() => {
    setModeState((prev) => {
      const next: ThemeMode = prev === 'dark' ? 'light' : 'dark'
      try { localStorage.setItem(STORAGE_KEY, next) } catch { /* swallow */ }
      applyAttribute(next)
      return next
    })
  }, [])

  const value = useMemo(() => ({ mode, setMode, toggle }), [mode, setMode, toggle])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
