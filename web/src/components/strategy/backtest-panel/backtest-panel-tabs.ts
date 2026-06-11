export type TabId = 'metrics' | 'positions' | 'equity'

export const TAB_IDS: ReadonlyArray<{ id: TabId; label: string }> = [
  { id: 'metrics', label: 'Metrics' },
  { id: 'positions', label: 'Positions' },
  { id: 'equity', label: 'Equity' },
]

export const STORAGE_KEY = 'backtest-panel.layout'

export interface PanelLayout {
  height: number
  collapsed: boolean
  activeTab: TabId
}

export const DEFAULT_LAYOUT: PanelLayout = {
  height: 280,
  collapsed: false,
  activeTab: 'metrics',
}

export const MIN_HEIGHT = 120
export const MAX_HEIGHT_VH = 0.6
