// Header button to flip dark / light theme. Self-contained via context.

import { useTheme } from '../../lib/use-theme'

export function ThemeToggle() {
  const { mode, toggle } = useTheme()
  const isDark = mode === 'dark'
  return (
    <button
      type="button"
      className="strategy-select"
      onClick={toggle}
      title={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
      aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
    >
      {isDark ? '☾' : '☀'}
    </button>
  )
}
