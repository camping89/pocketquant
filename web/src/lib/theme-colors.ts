// Bridge CSS theme tokens → lightweight-charts color strings. The charting lib
// takes literal color values (not `var(--…)`), so read the computed tokens off
// <html> at create-time and on every theme flip.

export interface ChartColors {
  background: string
  text: string
  grid: string
  border: string
  up: string
  down: string
}

// Dark-palette fallbacks if a token resolves empty (e.g. data-theme not yet set).
const FALLBACK: ChartColors = {
  background: '#1F1E1D',
  text: '#F5F4EE',
  grid: '#3A3937',
  border: '#3A3937',
  up: '#4A9782',
  down: '#C96442',
}

export function readChartColors(): ChartColors {
  const s = getComputedStyle(document.documentElement)
  const v = (name: string, fallback: string) => {
    const raw = s.getPropertyValue(name).trim()
    return raw || fallback
  }
  return {
    background: v('--bg-primary', FALLBACK.background),
    text: v('--text-primary', FALLBACK.text),
    grid: v('--border-color', FALLBACK.grid),
    border: v('--border-color', FALLBACK.border),
    up: v('--up-color', FALLBACK.up),
    down: v('--down-color', FALLBACK.down),
  }
}
