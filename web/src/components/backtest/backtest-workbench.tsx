import { useState, type PointerEvent as ReactPointerEvent } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { RunHistoryRail } from './run-history-rail'
import { BacktestDetailPane } from './backtest-detail-pane'

type MobileTab = 'list' | 'detail'

const MOBILE_TABS: { key: MobileTab; label: string }[] = [
  { key: 'list', label: 'List' },
  { key: 'detail', label: 'Detail' },
]

const RAIL_MIN = 260
const RAIL_MAX = 760
const RAIL_DEFAULT = 400
const RAIL_STORAGE_KEY = 'backtest-rail-width'

function clampRail(w: number) {
  return Math.min(RAIL_MAX, Math.max(RAIL_MIN, w))
}

/** Master-detail workbench. The selected run + active tab live in the path
 *  (`/backtest/<runId>/<tab>`, reload/back/forward safe); selecting a run
 *  navigates and, on mobile, flips to the Detail tab. */
export function BacktestWorkbench({
  selectedRun,
  activeTab,
}: {
  selectedRun: string | null
  activeTab?: string
}) {
  const navigate = useNavigate()
  const [mobileTab, setMobileTab] = useState<MobileTab>(selectedRun ? 'detail' : 'list')
  const [railWidth, setRailWidth] = useState(() => {
    const saved = Number(localStorage.getItem(RAIL_STORAGE_KEY))
    return saved ? clampRail(saved) : RAIL_DEFAULT
  })

  function startResize(e: ReactPointerEvent) {
    e.preventDefault()
    const startX = e.clientX
    const startW = railWidth
    function onMove(ev: PointerEvent) {
      setRailWidth(clampRail(startW + ev.clientX - startX))
    }
    function onUp() {
      document.removeEventListener('pointermove', onMove)
      document.removeEventListener('pointerup', onUp)
      document.body.style.cursor = ''
      setRailWidth((w) => {
        localStorage.setItem(RAIL_STORAGE_KEY, String(w))
        return w
      })
    }
    document.addEventListener('pointermove', onMove)
    document.addEventListener('pointerup', onUp)
    document.body.style.cursor = 'col-resize'
  }

  // Follow the run in the URL: back/forward or a fresh run (drawer submit) flips
  // the mobile tab even though they bypass handleSelect. Adjust-during-render so
  // the panes stay in sync without an effect.
  const [prevRun, setPrevRun] = useState(selectedRun)
  if (selectedRun !== prevRun) {
    setPrevRun(selectedRun)
    setMobileTab(selectedRun ? 'detail' : 'list')
  }

  function handleSelect(runId: string) {
    void navigate({ to: '/backtest/{-$runId}/{-$tab}', params: { runId, tab: undefined } })
  }

  function handleTab(tab: string) {
    if (selectedRun) {
      void navigate({ to: '/backtest/{-$runId}/{-$tab}', params: { runId: selectedRun, tab } })
    }
  }

  return (
    <>
      <div className="backtest-layout" style={{ gridTemplateColumns: `${railWidth}px 1fr` }}>
        <div className="backtest-list-pane">
          <RunHistoryRail selectedRun={selectedRun} onSelect={handleSelect} />
        </div>
        <div
          className="backtest-resizer"
          style={{ left: railWidth }}
          onPointerDown={startResize}
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize run list"
        />
        <div className="backtest-detail-pane">
          <BacktestDetailPane runId={selectedRun} activeTab={activeTab} onTabChange={handleTab} />
        </div>
      </div>

      <div className="backtest-mobile">
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
          {mobileTab === 'list' && <RunHistoryRail selectedRun={selectedRun} onSelect={handleSelect} />}
          {mobileTab === 'detail' && (
            <BacktestDetailPane runId={selectedRun} activeTab={activeTab} onTabChange={handleTab} />
          )}
        </div>
      </div>
    </>
  )
}
