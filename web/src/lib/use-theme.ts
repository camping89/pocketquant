// Hook for consuming ThemeContext. Split from `theme-context.tsx` to keep that
// file component-only (required by react-refresh ESLint rule).

import { useContext } from 'react'
import { ThemeContext, type ThemeContextValue } from './theme-context'

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>')
  return ctx
}
