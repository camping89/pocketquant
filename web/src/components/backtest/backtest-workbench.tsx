import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { RunHistoryRail } from './run-history-rail'
import { BacktestDetailPane } from './backtest-detail-pane'

type MobileTab = 'list' | 'detail'

const MOBILE_TABS: { key: MobileTab; label: string }[] = [
  { key: 'list', label: 'List' },
  { key: 'detail', label: 'Detail' },
]

/** Master-detail workbench. The selected run lives in the `?run=` search param
 *  (reload/back/forward safe); selecting a run navigates and, on mobile, flips
 *  to the Detail tab. */
export function BacktestWorkbench({ selectedRun }: { selectedRun: string | null }) {
  const navigate = useNavigate()
  const [mobileTab, setMobileTab] = useState<MobileTab>(selectedRun ? 'detail' : 'list')

  // Follow the run in the URL: back/forward or a fresh run (drawer submit) flips
  // the mobile tab even though they bypass handleSelect. Adjust-during-render so
  // the panes stay in sync without an effect.
  const [prevRun, setPrevRun] = useState(selectedRun)
  if (selectedRun !== prevRun) {
    setPrevRun(selectedRun)
    setMobileTab(selectedRun ? 'detail' : 'list')
  }

  function handleSelect(runId: string) {
    void navigate({ to: '/backtest', search: { run: runId } })
  }

  return (
    <>
      <div className="backtest-layout">
        <div className="backtest-list-pane">
          <RunHistoryRail selectedRun={selectedRun} onSelect={handleSelect} />
        </div>
        <div className="backtest-detail-pane">
          <BacktestDetailPane runId={selectedRun} />
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
          {mobileTab === 'detail' && <BacktestDetailPane runId={selectedRun} />}
        </div>
      </div>
    </>
  )
}
