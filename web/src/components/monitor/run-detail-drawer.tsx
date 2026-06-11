import { useEffect, useRef } from 'react'
import type { JobRun } from '../../types/job-history'
import { useFmt } from '../../lib/use-timezone'
import { statusColor, statusLabel } from './job-status-palette'

interface RunDetailDrawerProps {
  run: JobRun | null
  onClose: () => void
}

export function RunDetailDrawer({ run, onClose }: RunDetailDrawerProps) {
  const closeRef = useRef<HTMLButtonElement>(null)
  const fmt = useFmt()

  useEffect(() => {
    if (!run) return
    const previouslyFocused = document.activeElement as HTMLElement | null
    closeRef.current?.focus()
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      previouslyFocused?.focus?.()
    }
  }, [run, onClose])

  if (!run) return null

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} aria-hidden />
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label={`Run ${run._id}`}
      >
        <header className="drawer-header">
          <div>
            <span
              className="status-pill"
              style={{ backgroundColor: statusColor(run.status), color: '#0b1220' }}
            >
              {statusLabel(run.status)}
            </span>
            <span className="drawer-title mono">{run._id.slice(0, 12)}…</span>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="drawer-close"
            onClick={onClose}
            aria-label="Close drawer"
          >
            ✕
          </button>
        </header>
        <dl className="drawer-meta">
          <dt>Started</dt>
          <dd className="mono">{fmt.fullDateTime(run.started_at)}</dd>
          <dt>Finished</dt>
          <dd className="mono">{fmt.fullDateTime(run.finished_at)}</dd>
          <dt>Scheduled</dt>
          <dd className="mono">{fmt.fullDateTime(run.scheduled_run_time)}</dd>
          <dt>Duration</dt>
          <dd className="mono">{run.duration_ms ?? '—'} ms</dd>
          <dt>Inserted / Fetched</dt>
          <dd className="mono">
            {run.total_inserted ?? '—'} / {run.total_fetched ?? '—'}
          </dd>
        </dl>
        {run.error && (
          <pre className="drawer-error" aria-label="Run error">
            {run.error}
          </pre>
        )}
        <h4 className="drawer-section">Per-(symbol, interval) details</h4>
        {run.details.length === 0 ? (
          <p className="monitor-empty">No detail records (likely a missed/skipped tick).</p>
        ) : (
          <div className="table-wrap">
            <table className="monitor-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>TF</th>
                  <th className="num">Fetched</th>
                  <th className="num">Inserted</th>
                  <th className="num">Filt(exist)</th>
                  <th className="num">Filt(misalign)</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {run.details.map((d, i) => (
                  <tr key={`${d.symbol}-${d.interval}-${i}`}>
                    <td className="mono">{d.symbol}</td>
                    <td className="mono">{d.interval}</td>
                    <td className="num">{d.bars_fetched}</td>
                    <td className="num">{d.bars_inserted}</td>
                    <td className="num">{d.filtered_existing}</td>
                    <td className="num">{d.filtered_misaligned}</td>
                    <td title={d.error ?? ''}>
                      <span
                        className="status-pill"
                        style={{ backgroundColor: statusColor(d.status), color: '#0b1220' }}
                      >
                        {statusLabel(d.status)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <details className="drawer-raw">
          <summary>Raw JSON</summary>
          <pre>{JSON.stringify(run, null, 2)}</pre>
        </details>
      </aside>
    </>
  )
}
