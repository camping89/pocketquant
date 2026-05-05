import type { JobRunStatus } from '../../types/job-history'

const STATUSES: JobRunStatus[] = [
  'completed',
  'running',
  'missed',
  'skipped_max_instances',
  'failed',
]

const WINDOWS = ['24h', '7d', '30d'] as const
type Window = (typeof WINDOWS)[number]

interface JobFiltersBarProps {
  window: Window
  status: string | undefined
  onWindowChange: (w: Window) => void
  onStatusChange: (s: string | undefined) => void
}

export function JobFiltersBar({ window, status, onWindowChange, onStatusChange }: JobFiltersBarProps) {
  return (
    <div className="job-filters-bar">
      <div className="filter-group">
        <span className="filter-label">Window:</span>
        {WINDOWS.map((w) => (
          <button
            key={w}
            type="button"
            className={`filter-chip${w === window ? ' active' : ''}`}
            onClick={() => onWindowChange(w)}
          >
            {w}
          </button>
        ))}
      </div>
      <div className="filter-group">
        <span className="filter-label">Status:</span>
        <button
          type="button"
          className={`filter-chip${!status ? ' active' : ''}`}
          onClick={() => onStatusChange(undefined)}
        >
          all
        </button>
        {STATUSES.map((s) => (
          <button
            key={s}
            type="button"
            className={`filter-chip${status === s ? ' active' : ''}`}
            onClick={() => onStatusChange(s)}
          >
            {s.replace('_', ' ')}
          </button>
        ))}
      </div>
    </div>
  )
}
