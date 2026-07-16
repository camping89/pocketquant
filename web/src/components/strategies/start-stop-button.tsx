/**
 * Primary action button for starting/stopping a strategy subscription.
 * Stop variant shows an AlertDialog confirmation before mutating.
 */
import { useState } from 'react'

interface StartStopButtonProps {
  isRunning: boolean
  isLoading: boolean
  onStart: () => void
  onStop: () => void
  disabled?: boolean
}

export function StartStopButton({
  isRunning,
  isLoading,
  onStart,
  onStop,
  disabled = false,
}: StartStopButtonProps) {
  const [confirmOpen, setConfirmOpen] = useState(false)

  if (isRunning) {
    return (
      <>
        <button type="button"
          className="btn"
          disabled={isLoading || disabled}
          onClick={() => setConfirmOpen(true)}
          style={{
            color: '#ef5350',
            borderColor: 'rgba(239,83,80,0.4)',
            padding: '4px 14px',
            fontSize: 12,
          }}
        >
          {isLoading ? 'Stopping…' : 'Stop'}
        </button>

        {confirmOpen && (
          <div
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(0,0,0,.6)',
              zIndex: 300,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            onClick={(e) => { if (e.target === e.currentTarget) setConfirmOpen(false) }}
          >
            <div
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-color)',
                borderRadius: 8,
                padding: '20px 24px',
                width: 300,
                boxShadow: '0 8px 32px rgba(0,0,0,.5)',
              }}
            >
              <p style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: 'var(--text-primary)' }}>
                Stop strategy?
              </p>
              <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 20 }}>
                This will halt live execution. Open positions will remain unchanged.
              </p>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button type="button" className="btn" onClick={() => setConfirmOpen(false)}>Cancel</button>
                <button type="button"
                  className="btn"
                  disabled={isLoading}
                  onClick={() => { setConfirmOpen(false); onStop() }}
                  style={{ color: '#ef5350', borderColor: 'rgba(239,83,80,0.4)' }}
                >
                  {isLoading ? 'Stopping…' : 'Stop'}
                </button>
              </div>
            </div>
          </div>
        )}
      </>
    )
  }

  return (
    <button type="button"
      className="btn-sm"
      disabled={isLoading || disabled}
      onClick={onStart}
      style={{ padding: '4px 14px', fontSize: 12 }}
    >
      {isLoading ? 'Starting…' : 'Start'}
    </button>
  )
}
