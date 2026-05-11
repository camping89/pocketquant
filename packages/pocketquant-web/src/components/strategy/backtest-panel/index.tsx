import { useCallback, useEffect, useRef } from 'react'
import type { IChartApi } from 'lightweight-charts'
import type { BacktestPosition, SubscriptionBacktest } from '../../../api/backtest-api'
import { BacktestPanelHeader } from './backtest-panel-header'
import { EquityTab } from './equity-tab'
import { MetricsTab } from './metrics-tab'
import { PositionsTab } from './positions-tab'
import { clampHeight, usePanelLayout } from './use-panel-layout'

interface BacktestPanelProps {
  backtest: SubscriptionBacktest
  chart?: IChartApi | null
  highlightedPositionIndex?: number | null
  onPositionClick?: (index: number, position: BacktestPosition) => void
  onPositionHover?: (index: number | null, position: BacktestPosition | null) => void
}

export function BacktestPanel({
  backtest,
  chart = null,
  highlightedPositionIndex = null,
  onPositionClick,
  onPositionHover,
}: BacktestPanelProps) {
  const { layout, setHeight, toggleCollapsed, setActiveTab } = usePanelLayout()
  const draggingRef = useRef(false)

  const onMouseDown = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      e.preventDefault()
      draggingRef.current = true
      document.body.style.cursor = 'row-resize'
      document.body.style.userSelect = 'none'
    },
    [],
  )

  useEffect(() => {
    function onMove(e: MouseEvent) {
      if (!draggingRef.current) return
      const next = window.innerHeight - e.clientY
      setHeight(clampHeight(next))
    }
    function onUp() {
      if (!draggingRef.current) return
      draggingRef.current = false
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [setHeight])

  const contentHeight = layout.collapsed ? 0 : layout.height

  const renderStatusPlaceholder = () => {
    const status = backtest.status
    if (status === 'running' || status === 'pending') {
      return (
        <div className="backtest-panel__tab-content">
          <div className="empty-state">
            <div className="loading-spinner" />
            <div>Backtest {status === 'running' ? 'running' : 'queued'}…</div>
          </div>
        </div>
      )
    }
    if (status === 'failed') {
      const msg = backtest.error_msg ?? backtest.error_message ?? 'Backtest engine error'
      return (
        <div className="backtest-panel__tab-content">
          <div className="empty-state empty-state--error">
            <div>✗ Backtest failed</div>
            <div className="empty-state__sub">{msg}</div>
          </div>
        </div>
      )
    }
    return null
  }

  const renderTab = () => {
    const placeholder = renderStatusPlaceholder()
    if (placeholder) return placeholder
    switch (layout.activeTab) {
      case 'metrics':
        return <MetricsTab backtest={backtest} />
      case 'positions':
        return (
          <PositionsTab
            backtest={backtest}
            highlightedIndex={highlightedPositionIndex}
            onPositionClick={onPositionClick}
            onPositionHover={onPositionHover}
          />
        )
      case 'equity':
        return <EquityTab backtest={backtest} chart={chart} />
    }
  }

  const statusLabel = backtest.status === 'completed' ? undefined : `Status: ${backtest.status}`

  return (
    <div className="backtest-panel" style={{ height: contentHeight + 32 + (layout.collapsed ? 0 : 4) }}>
      {!layout.collapsed && (
        <div className="backtest-panel__drag-handle" onMouseDown={onMouseDown} />
      )}
      <BacktestPanelHeader
        activeTab={layout.activeTab}
        collapsed={layout.collapsed}
        onTabChange={setActiveTab}
        onToggleCollapsed={toggleCollapsed}
        status={statusLabel}
      />
      {!layout.collapsed && (
        <div className="backtest-panel__content" style={{ height: contentHeight }}>
          {renderTab()}
        </div>
      )}
    </div>
  )
}
