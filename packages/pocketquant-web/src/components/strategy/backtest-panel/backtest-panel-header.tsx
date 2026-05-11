import { TAB_IDS, type TabId } from './backtest-panel-tabs'

interface BacktestPanelHeaderProps {
  activeTab: TabId
  collapsed: boolean
  onTabChange: (tab: TabId) => void
  onToggleCollapsed: () => void
  status?: string
}

export function BacktestPanelHeader({
  activeTab,
  collapsed,
  onTabChange,
  onToggleCollapsed,
  status,
}: BacktestPanelHeaderProps) {
  return (
    <div className="backtest-panel__header">
      <div className="backtest-panel__tabs">
        {TAB_IDS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`backtest-panel__tab${activeTab === tab.id ? ' backtest-panel__tab--active' : ''}`}
            onClick={() => onTabChange(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="backtest-panel__header-right">
        {status && <span className="backtest-panel__status">{status}</span>}
        <button
          type="button"
          className="backtest-panel__collapse-btn"
          aria-label={collapsed ? 'Expand panel' : 'Collapse panel'}
          onClick={onToggleCollapsed}
        >
          {collapsed ? '▲' : '▼'}
        </button>
      </div>
    </div>
  )
}
