import { useState } from 'react'
import type { BacktestRunResult } from '../../api/backtest-api'
import { MetricsTab } from '../strategy/backtest-panel/metrics-tab'
import { PositionsTab } from '../strategy/backtest-panel/positions-tab'
import { EquitySparkline } from '../strategies/equity-sparkline'

type ResultTab = 'metrics' | 'equity' | 'positions'

const TABS: { key: ResultTab; label: string }[] = [
  { key: 'metrics', label: 'Metrics' },
  { key: 'equity', label: 'Equity' },
  { key: 'positions', label: 'Trades' },
]

export function BacktestResultView({ run }: { run: BacktestRunResult }) {
  const [tab, setTab] = useState<ResultTab>('metrics')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div
        style={{
          display: 'flex',
          gap: 2,
          padding: '4px 0',
          borderBottom: '1px solid var(--border-color)',
        }}
      >
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            className={`backtest-panel__tab${tab === key ? ' backtest-panel__tab--active' : ''}`}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'metrics' && <MetricsTab backtest={run} />}
      {tab === 'equity' && (
        <div style={{ padding: '8px 0' }}>
          <EquitySparkline equityCurve={run.equity_curve} width={600} />
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 6 }}>
            {run.equity_curve.length} points
          </div>
        </div>
      )}
      {tab === 'positions' && <PositionsTab backtest={run} highlightedIndex={null} />}
    </div>
  )
}
