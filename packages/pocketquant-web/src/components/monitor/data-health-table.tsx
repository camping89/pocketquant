import { useEffect, useMemo, useState } from 'react'
import { checkIntegrity } from '../../api/monitor-api'
import { INTERVAL_ORDER } from '../../hooks/use-available-intervals'
import { useIntegrityRepair } from '../../hooks/use-integrity'
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
  const repair = useIntegrityRepair()
  const [rowStates, setRowStates] = useState<Record<string, RowState>>({})
  const [daysBack, setDaysBack] = useState(7)

  const filtered = useMemo(() => {
    if (!data?.length) return []
    const rows = data.filter((s) => s.exchange === exchange && s.symbol === symbol)
    return rows.sort(
      (a, b) =>
        INTERVAL_ORDER.indexOf(a.interval as (typeof INTERVAL_ORDER)[number]) -
        INTERVAL_ORDER.indexOf(b.interval as (typeof INTERVAL_ORDER)[number]),
    )
  }, [data, exchange, symbol])

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
  const ago = dataUpdatedAt ? formatAge(new Date(dataUpdatedAt).toISOString()) : ''

  const defaultRow: RowState = { expanded: false, checking: false, repairing: false }

  function getRow(key: string): RowState {
    return rowStates[key] ?? defaultRow
  }

  function updateRow(key: string, patch: Partial<RowState>) {
    setRowStates((prev) => {
      const current = prev[key] ?? defaultRow
      return { ...prev, [key]: { ...current, ...patch } }
    })
  }

  async function handleCheck(s: typeof filtered[0]) {
    const key = s.interval
    updateRow(key, { checking: true })
    try {
      const report = await checkIntegrity(s.symbol, s.exchange, s.interval, daysBack)
      updateRow(key, { report, checking: false })
    } catch {
      updateRow(key, { checking: false })
    }
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

  const isCheckingAny = filtered.some((s) => getRow(s.interval).checking)

  function handleCheckAll() {
    for (const s of filtered) {
      if (!getRow(s.interval).checking) handleCheck(s)
    }
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
        <div className="section-actions">
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
          <button
            className="btn-sm"
            onClick={handleCheckAll}
            disabled={isCheckingAny || filtered.length === 0}
          >
            {isCheckingAny ? 'Checking…' : 'Check All'}
          </button>
        </div>
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
