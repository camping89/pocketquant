import { useEffect, useState } from 'react'
import { useIntegrityCheck, useIntegrityRepair } from '../../hooks/use-integrity'
import { useSyncStatus } from '../../hooks/use-sync-status'
import type { IntegrityReport, RepairResult } from '../../types/market-data'
import { DataHealthRow } from './data-health-row'
import { formatAge } from './format-helpers'

interface RowState {
  report?: IntegrityReport
  repair?: RepairResult
  expanded: boolean
  checking: boolean
  repairing: boolean
}

interface IntegrityTotals {
  misaligned: number
  gaps: number
}

interface DataHealthTableProps {
  exchange: string
  symbol: string
  onIntegrityUpdate?: (totals: IntegrityTotals | null) => void
}

export function DataHealthTable({ exchange, symbol, onIntegrityUpdate }: DataHealthTableProps) {
  const { data, isLoading, error, dataUpdatedAt } = useSyncStatus()
  const check = useIntegrityCheck()
  const repair = useIntegrityRepair()
  const [rowStates, setRowStates] = useState<Record<string, RowState>>({})
  const [daysBack, setDaysBack] = useState(7)

  useEffect(() => {
    if (!onIntegrityUpdate) return
    let totalMisaligned = 0
    let totalGaps = 0
    let hasAny = false
    for (const rs of Object.values(rowStates)) {
      if (rs.report) {
        hasAny = true
        totalMisaligned += rs.report.misaligned_count
        totalGaps += rs.report.missing_count
      }
    }
    onIntegrityUpdate(hasAny ? { misaligned: totalMisaligned, gaps: totalGaps } : null)
  }, [rowStates, onIntegrityUpdate])

  if (isLoading) return <div className="monitor-loading">Loading data health...</div>
  if (error) return <div className="monitor-error">Failed to load: {error.message}</div>
  if (!data?.length) return <div className="monitor-empty">No symbols tracked</div>

  const filtered = data.filter((s) => s.exchange === exchange && s.symbol === symbol)
  const ago = dataUpdatedAt ? formatAge(new Date(dataUpdatedAt).toISOString()) : ''

  function getRow(key: string): RowState {
    return rowStates[key] ?? { expanded: false, checking: false, repairing: false }
  }

  function updateRow(key: string, patch: Partial<RowState>) {
    setRowStates((prev) => ({ ...prev, [key]: { ...getRow(key), ...patch } }))
  }

  function handleCheck(s: typeof filtered[0]) {
    const key = s.interval
    updateRow(key, { checking: true })
    check.mutate(
      { symbol: s.symbol, exchange: s.exchange, interval: s.interval, daysBack },
      {
        onSuccess: (report) => updateRow(key, { report, checking: false }),
        onError: () => updateRow(key, { checking: false }),
      },
    )
  }

  function handleRepair(s: typeof filtered[0]) {
    if (!confirm(`Repair ${s.symbol} ${s.interval}? This deletes misaligned bars and resyncs gaps.`)) return
    const key = s.interval
    updateRow(key, { repairing: true })
    repair.mutate(
      { symbol: s.symbol, exchange: s.exchange, interval: s.interval, daysBack },
      {
        onSuccess: (result) => updateRow(key, { repair: result, repairing: false }),
        onError: () => updateRow(key, { repairing: false }),
      },
    )
  }

  const totals = filtered.reduce(
    (acc, s) => {
      const rs = getRow(s.interval)
      if (rs.report) {
        acc.misaligned += rs.report.misaligned_count
        acc.gaps += rs.report.missing_count
        acc.checked++
      }
      return acc
    },
    { misaligned: 0, gaps: 0, checked: 0 },
  )

  return (
    <section className="monitor-section monitor-card">
      <div className="section-header">
        <h3>Data Health</h3>
        {ago && <span className="refresh-indicator">updated {ago} ago</span>}
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
      {filtered.length === 0 ? (
        <div className="monitor-empty">No sync data for {exchange}:{symbol}</div>
      ) : (
        <div className="table-wrap">
          <table className="monitor-table">
            <thead>
              <tr>
                <th>TF</th>
                <th>Bars</th>
                <th>Last Bar</th>
                <th>Age</th>
                <th>Integrity</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => {
                const key = s.interval
                const rs = getRow(key)
                return (
                  <DataHealthRow
                    key={key}
                    syncStatus={s}
                    report={rs.report}
                    repair={rs.repair}
                    expanded={rs.expanded}
                    checking={rs.checking}
                    repairing={rs.repairing}
                    onToggle={() => updateRow(key, { expanded: !rs.expanded })}
                    onCheck={() => handleCheck(s)}
                    onRepair={() => handleRepair(s)}
                  />
                )
              })}
            </tbody>
            {totals.checked > 0 && (
              <tfoot>
                <tr>
                  <td colSpan={4} />
                  <td>
                    {totals.misaligned + totals.gaps === 0
                      ? 'All OK'
                      : `${totals.misaligned} misaligned \u00b7 ${totals.gaps} gaps`}
                  </td>
                  <td colSpan={2} />
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}
    </section>
  )
}
