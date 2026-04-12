import { useState } from 'react'
import { useSyncStatus } from '../../hooks/use-sync-status'
import { useIntegrityCheck, useIntegrityRepair } from '../../hooks/use-integrity'
import type { SyncStatus, IntegrityReport, RepairResult } from '../../types/market-data'

interface RowState {
  report?: IntegrityReport
  repair?: RepairResult
}

function IntegrityRow({
  s,
  daysBack,
}: {
  s: SyncStatus
  daysBack: number
}) {
  const check = useIntegrityCheck()
  const repair = useIntegrityRepair()
  const [state, setState] = useState<RowState>({})

  const hasIssues = state.report &&
    (state.report.misaligned_count > 0 || state.report.missing_count > 0)

  function handleCheck() {
    check.mutate(
      { symbol: s.symbol, exchange: s.exchange, interval: s.interval, daysBack },
      { onSuccess: (report) => setState({ report }) },
    )
  }

  function handleRepair() {
    if (!confirm(`Repair ${s.symbol} ${s.interval}? This deletes misaligned bars and resyncs gaps.`)) return
    repair.mutate(
      { symbol: s.symbol, exchange: s.exchange, interval: s.interval, daysBack },
      { onSuccess: (result) => setState((prev) => ({ ...prev, repair: result })) },
    )
  }

  return (
    <tr>
      <td className="mono">{s.interval}</td>
      <td className="num">{state.report ? state.report.misaligned_count : '—'}</td>
      <td className="num">{state.report ? state.report.missing_count : '—'}</td>
      <td className="actions">
        <button className="btn btn-neutral" disabled={check.isPending} onClick={handleCheck}>
          {check.isPending ? '...' : 'Check'}
        </button>
        {hasIssues && !state.repair && (
          <button className="btn btn-warn" disabled={repair.isPending} onClick={handleRepair}>
            {repair.isPending ? '...' : 'Repair'}
          </button>
        )}
        {state.repair && (
          <span className="repair-result">
            Deleted {state.repair.deleted}, resynced {state.repair.gaps_resynced} gaps
          </span>
        )}
      </td>
    </tr>
  )
}

interface IntegrityPanelProps {
  exchange: string
  symbol: string
}

export function IntegrityPanel({ exchange, symbol }: IntegrityPanelProps) {
  const { data: syncData } = useSyncStatus()
  const [daysBack, setDaysBack] = useState(7)

  if (!syncData?.length) return null

  const filtered = syncData.filter((s) => s.exchange === exchange && s.symbol === symbol)

  return (
    <section className="monitor-section">
      <div className="section-header">
        <h3>Bar Integrity</h3>
        <label className="days-input">
          Days back:
          <input
            type="number"
            min={1}
            max={90}
            value={daysBack}
            onChange={(e) => setDaysBack(Math.max(1, Math.min(90, Number(e.target.value) || 1)))}
          />
        </label>
      </div>
      <div className="table-wrap">
        <table className="monitor-table">
          <thead>
            <tr>
              <th>TF</th><th>Misaligned</th><th>Gaps</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((s) => (
              <IntegrityRow
                key={`${s.exchange}:${s.symbol}:${s.interval}`}
                s={s}
                daysBack={daysBack}
              />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
