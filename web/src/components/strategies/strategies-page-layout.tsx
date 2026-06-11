/**
 * 3-pane CSS Grid wrapper for the strategies operator dashboard.
 * Desktop: 240px sidebar | 1fr main | 360px dashboard
 * Mobile <768px: tab-controlled single pane view.
 */
import { useState, useMemo } from 'react'
import { StrategyListSidebar } from './strategy-list-sidebar'
import { StrategyConfigCard } from './strategy-config-card'
import { DashboardColumn } from './dashboard-column'
import { StrategyChart } from './strategy-chart'
import { useStrategyTrades } from '../../hooks/use-strategy-trades'
import { useOpenPosition } from '../../hooks/use-open-position'
import type { Subscription } from '../../api/strategy-api'
import type { Interval } from '../../types/market-data'
import type { Trade, OpenPosition as ChartOpenPosition } from '../../types/strategy'

type MobileTab = 'list' | 'config' | 'dashboard'

const MOBILE_TABS: { key: MobileTab; label: string }[] = [
  { key: 'list', label: 'List' },
  { key: 'config', label: 'Config' },
  { key: 'dashboard', label: 'Dashboard' },
]

export function StrategiesPageLayout() {
  const [selectedSub, setSelectedSub] = useState<Subscription | null>(null)
  const [mobileTab, setMobileTab] = useState<MobileTab>('list')

  const { data: rawTrades = [] } = useStrategyTrades(selectedSub?.id ?? null)
  const { data: apiPosition = null } = useOpenPosition(selectedSub?.id ?? null)

  /**
   * Adapt StrategyTrade[] (table shape from recent-trades-table) to Trade[]
   * (chart marker shape). The table shape uses direction/entry_price/exit_price;
   * we emit one entry marker and one exit marker per closed trade.
   * TODO(backend): once the /trades endpoint returns Trade shape directly,
   * remove this adapter and type rawTrades as Trade[].
   */
  const trades = useMemo<Trade[]>(() => {
    const result: Trade[] = []
    for (const t of rawTrades) {
      result.push({
        timestamp: t.entry_time,
        side: t.direction.toLowerCase() as 'long' | 'short',
        is_entry: true,
        qty: t.quantity,
        price: t.entry_price,
      })
      if (t.exit_time && t.exit_price != null) {
        result.push({
          timestamp: t.exit_time,
          side: t.direction.toLowerCase() as 'long' | 'short',
          is_entry: false,
          qty: t.quantity,
          price: t.exit_price,
        })
      }
    }
    return result
  }, [rawTrades])

  /**
   * Adapt API OpenPosition (direction: 'LONG'|'SHORT') to chart OpenPosition
   * (side: 'long'|'short'). Returns null when no open position.
   */
  const openPos = useMemo<ChartOpenPosition | null>(() => {
    if (!apiPosition) return null
    return {
      side: apiPosition.direction.toLowerCase() as 'long' | 'short',
      entry_price: apiPosition.entry_price,
      liq_price: apiPosition.liq_price ?? null,
      leverage: apiPosition.leverage ?? 1,
      qty: apiPosition.quantity,
    }
  }, [apiPosition])

  function handleSelectSub(sub: Subscription) {
    setSelectedSub((prev) => (prev?.id === sub.id ? null : sub))
    setMobileTab('config')
  }

  const emptyCenter = (
    <div
      style={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'var(--text-secondary)',
        fontSize: 13,
      }}
    >
      Select a subscription from the list.
    </div>
  )

  return (
    <>
      <div className="strategies-layout">
        <div className="strategies-sidebar">
          <StrategyListSidebar
            selectedSubId={selectedSub?.id ?? null}
            onSelect={handleSelectSub}
          />
        </div>

        <main className="strategies-main">
          {selectedSub ? (
            <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
              {/* Embedded chart — locked to subscription's symbol + interval */}
              <div style={{ height: 400, flexShrink: 0 }}>
                <StrategyChart
                  symbol={selectedSub.symbol}
                  interval={selectedSub.interval as Interval}
                  trades={trades}
                  openPosition={openPos}
                />
              </div>
              <div style={{ padding: 16, overflowY: 'auto', flex: 1 }}>
                <StrategyConfigCard sub={selectedSub} onDeleted={() => setSelectedSub(null)} />
              </div>
            </div>
          ) : (
            emptyCenter
          )}
        </main>

        <div className="strategies-dashboard">
          {selectedSub ? (
            <DashboardColumn sub={selectedSub} />
          ) : (
            <div
              style={{
                height: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--text-secondary)',
                fontSize: 12,
                borderLeft: '1px solid var(--border-color)',
              }}
            >
              No subscription selected.
            </div>
          )}
        </div>
      </div>

      <div className="strategies-mobile">
        <div className="strategies-mobile__tabs">
          {MOBILE_TABS.map(({ key, label }) => (
            <button
              key={key}
              className={`strategies-mobile__tab${mobileTab === key ? ' strategies-mobile__tab--active' : ''}`}
              onClick={() => setMobileTab(key)}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="strategies-mobile__pane">
          {mobileTab === 'list' && (
            <StrategyListSidebar
              selectedSubId={selectedSub?.id ?? null}
              onSelect={handleSelectSub}
            />
          )}
          {mobileTab === 'config' && (
            selectedSub ? (
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <div style={{ height: 300 }}>
                  <StrategyChart
                    symbol={selectedSub.symbol}
                    interval={selectedSub.interval as Interval}
                    trades={trades}
                    openPosition={openPos}
                  />
                </div>
                <div style={{ padding: 16 }}>
                  <StrategyConfigCard sub={selectedSub} onDeleted={() => setSelectedSub(null)} />
                </div>
              </div>
            ) : emptyCenter
          )}
          {mobileTab === 'dashboard' && (
            selectedSub ? (
              <DashboardColumn sub={selectedSub} />
            ) : (
              <div style={{ padding: 16, color: 'var(--text-secondary)', fontSize: 13 }}>
                No subscription selected.
              </div>
            )
          )}
        </div>
      </div>
    </>
  )
}
