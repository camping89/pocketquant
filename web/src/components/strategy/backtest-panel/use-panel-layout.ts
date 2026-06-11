import { useCallback, useEffect, useState } from 'react'
import {
  DEFAULT_LAYOUT,
  MAX_HEIGHT_VH,
  MIN_HEIGHT,
  STORAGE_KEY,
  type PanelLayout,
  type TabId,
} from './backtest-panel-tabs'

function readLayout(): PanelLayout {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_LAYOUT
    const parsed = JSON.parse(raw) as Partial<PanelLayout>
    return {
      height: typeof parsed.height === 'number' ? parsed.height : DEFAULT_LAYOUT.height,
      collapsed: typeof parsed.collapsed === 'boolean' ? parsed.collapsed : DEFAULT_LAYOUT.collapsed,
      activeTab: (['metrics', 'positions', 'equity'] as TabId[]).includes(parsed.activeTab as TabId)
        ? (parsed.activeTab as TabId)
        : DEFAULT_LAYOUT.activeTab,
    }
  } catch {
    return DEFAULT_LAYOUT
  }
}

function writeLayout(layout: PanelLayout): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(layout))
  } catch {
    // ignore quota / private-mode errors
  }
}

export function clampHeight(h: number): number {
  const max = typeof window !== 'undefined' ? window.innerHeight * MAX_HEIGHT_VH : 800
  return Math.min(Math.max(h, MIN_HEIGHT), max)
}

export function usePanelLayout(): {
  layout: PanelLayout
  setHeight: (h: number) => void
  toggleCollapsed: () => void
  setActiveTab: (tab: TabId) => void
} {
  const [layout, setLayout] = useState<PanelLayout>(() => readLayout())

  useEffect(() => {
    writeLayout(layout)
  }, [layout])

  const setHeight = useCallback((h: number) => {
    setLayout((prev) => ({ ...prev, height: clampHeight(h) }))
  }, [])

  const toggleCollapsed = useCallback(() => {
    setLayout((prev) => ({ ...prev, collapsed: !prev.collapsed }))
  }, [])

  const setActiveTab = useCallback((tab: TabId) => {
    setLayout((prev) => ({ ...prev, activeTab: tab }))
  }, [])

  return { layout, setHeight, toggleCollapsed, setActiveTab }
}
