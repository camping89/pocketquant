// The query and both mutations live here because this is their only caller.
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, apiPost } from '../../api/api-client'
import { moneyHint } from '../../lib/money-hint'
import { ConfirmDialog } from './start-stop-button'

// Mirrors the backend Safeguards dataclass.
interface Safeguards {
  live_trading: boolean
  daily_loss_cap: number | null
  max_lots: number | null
  leverage: number
  risk_per_trade: number
  entries_paused: boolean
}

const SAFEGUARDS_KEY = ['safeguards']
const PAUSE_HINT = moneyHint('exness', 'pause')
const RESUME_HINT = moneyHint('exness', 'resume')

export function ExnessStrip() {
  const qc = useQueryClient()
  const [confirmOpen, setConfirmOpen] = useState(false)

  const query = useQuery({
    queryKey: SAFEGUARDS_KEY,
    queryFn: () => apiFetch<Safeguards>('/api/v1/admin/safeguards'),
    refetchInterval: 5_000,
  })
  const onSuccess = () => qc.invalidateQueries({ queryKey: SAFEGUARDS_KEY })
  const pauseMut = useMutation({
    mutationFn: () => apiPost<Safeguards>('/api/v1/admin/safeguards/pause', {}),
    onSuccess,
  })
  const resumeMut = useMutation({
    mutationFn: () => apiPost<Safeguards>('/api/v1/admin/safeguards/resume', {}),
    onSuccess,
  })

  // Unknown state (loading or failed GET) shows "—" and keeps Pause available.
  // A failed refetch keeps the last data in the cache, so drop it explicitly.
  const data = query.isError ? undefined : query.data
  const paused = data?.entries_paused ?? false
  const capText = !data ? '—' : data.daily_loss_cap === null ? 'not set' : `${data.daily_loss_cap} USD`
  const lotsText = !data ? '—' : data.max_lots === null ? 'minimum lot' : String(data.max_lots)
  const capPhrase = data?.daily_loss_cap == null ? 'no daily loss cap' : `the ${capText} daily loss cap`
  const lotsPhrase = data?.max_lots == null ? 'the minimum lot size' : `${lotsText} max lots`
  const isPending = pauseMut.isPending || resumeMut.isPending
  const error = (pauseMut.error ?? resumeMut.error) as Error | null

  return (
    <section className="exness-strip" aria-label="Exness safeguards">
      <b>Exness</b>
      <span>
        <span className="exness-strip__key">live_trading:</span>{' '}
        {data ? (
          <span className={`exness-strip__chip exness-strip__chip--${data.live_trading ? 'on' : 'off'}`}>
            {data.live_trading ? 'ON' : 'OFF'}
          </span>
        ) : '—'}
      </span>
      <span>
        <span className="exness-strip__key">daily loss cap:</span>{' '}
        <span className="exness-strip__value">{capText}</span>
      </span>
      <span>
        <span className="exness-strip__key">max lots:</span>{' '}
        <span className="exness-strip__value">{lotsText}</span>
      </span>
      {paused && (
        <span className="exness-strip__chip exness-strip__chip--paused" role="status">Entries paused</span>
      )}

      <div className="exness-strip__actions">
        {error && <span role="alert" style={{ color: '#ef5350', fontSize: 11 }}>{error.message}</span>}
        <span className="risk risk-real" title={paused ? RESUME_HINT.title : PAUSE_HINT.title}>Real money</span>
        {paused ? (
          <button type="button"
            className="btn-sm"
            disabled={isPending}
            title={RESUME_HINT.title}
            onClick={() => setConfirmOpen(true)}
          >
            Resume
          </button>
        ) : (
          <button type="button"
            className="btn btn-warn"
            disabled={isPending}
            title={PAUSE_HINT.title}
            onClick={() => { resumeMut.reset(); pauseMut.mutate() }}
          >
            {pauseMut.isPending ? 'Pausing…' : 'Pause'}
          </button>
        )}
      </div>

      {confirmOpen && (
        <ConfirmDialog
          heading="Re-enable real-money entries?"
          chip={<span className="risk risk-real">{RESUME_HINT.chip}</span>}
          confirm={
            <button type="button"
              className="btn btn-danger"
              disabled={isPending}
              title={RESUME_HINT.title}
              onClick={() => { setConfirmOpen(false); pauseMut.reset(); resumeMut.mutate() }}
            >
              Resume entries
            </button>
          }
          onCancel={() => setConfirmOpen(false)}
        >
          <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 12, lineHeight: 1.5 }}>
            New Exness entries will be allowed again, within {capPhrase} and {lotsPhrase}.
          </p>
        </ConfirmDialog>
      )}
    </section>
  )
}
