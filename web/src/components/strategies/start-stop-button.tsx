/**
 * Primary action button for starting/stopping a strategy subscription.
 * Stop always confirms; Start confirms only on Exness (real orders).
 * Paper Start is one click. The dialog copy depends on the broker.
 */
import { useId, useState, type ReactNode } from 'react'
import { moneyHint, type Broker } from '../../lib/money-hint'

interface StartStopButtonProps {
  isRunning: boolean
  isLoading: boolean
  onStart: () => void
  onStop: () => void
  broker: Broker
  /** "<code> · <interval>", used in the dialog copy. */
  label: string
  disabled?: boolean
}

export function StartStopButton({
  isRunning,
  isLoading,
  onStart,
  onStop,
  broker,
  label,
  disabled = false,
}: StartStopButtonProps) {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const live = broker === 'exness'
  const hint = moneyHint(broker, isRunning ? 'stop' : 'start')

  const dialog = isRunning
    ? {
        heading: live ? 'Stop live strategy?' : 'Stop paper strategy?',
        body: live ? (
          <>
            <p style={bodyStyle}>
              This stops real-money execution on Exness for {label}. Open positions will remain unchanged.
            </p>
            <p style={bodyStyle}>
              To block new entries but keep the strategy warm, use Pause in the Exness strip.
            </p>
          </>
        ) : (
          <p style={bodyStyle}>
            This stops paper trading for {label}. Open paper positions will remain unchanged.
          </p>
        ),
        confirm: (
          <button type="button"
            className="btn btn-danger"
            disabled={isLoading}
            title={hint.title}
            onClick={() => { setConfirmOpen(false); onStop() }}
          >
            {isLoading ? 'Stopping…' : 'Stop'}
          </button>
        ),
      }
    : {
        heading: `Start real-money orders on Exness for ${label}?`,
        body: (
          <p style={bodyStyle}>
            Real orders go to Exness within the daily loss cap and max lots shown in the Exness strip.
          </p>
        ),
        confirm: (
          <button type="button"
            className="btn-sm"
            disabled={isLoading}
            title={hint.title}
            onClick={() => { setConfirmOpen(false); onStart() }}
          >
            {isLoading ? 'Starting…' : 'Start'}
          </button>
        ),
      }

  return (
    <>
      {isRunning ? (
        <button type="button"
          className="btn btn-danger"
          disabled={isLoading || disabled}
          title={hint.title}
          onClick={() => setConfirmOpen(true)}
          style={{ padding: '4px 14px', fontSize: 12 }}
        >
          {isLoading ? 'Stopping…' : 'Stop'}
        </button>
      ) : (
        <button type="button"
          className="btn-sm"
          disabled={isLoading || disabled}
          title={hint.title}
          onClick={live ? () => setConfirmOpen(true) : onStart}
          style={{ padding: '4px 14px', fontSize: 12 }}
        >
          {isLoading ? 'Starting…' : 'Start'}
        </button>
      )}

      {confirmOpen && (
        <ConfirmDialog
          heading={dialog.heading}
          chip={<span className={`risk ${hint.real ? 'risk-real' : 'risk-paper'}`}>{hint.chip}</span>}
          confirm={dialog.confirm}
          onCancel={() => setConfirmOpen(false)}
        >
          {dialog.body}
        </ConfirmDialog>
      )}
    </>
  )
}

const bodyStyle: React.CSSProperties = {
  fontSize: 12,
  color: 'var(--text-secondary)',
  marginBottom: 12,
  lineHeight: 1.5,
}

interface ConfirmDialogProps {
  heading: string
  children: ReactNode
  chip: ReactNode
  confirm: ReactNode
  onCancel: () => void
}

/** Modal with Cancel, then the money chip just left of the confirm button. Shared with the Exness strip. */
export function ConfirmDialog({ heading, children, chip, confirm, onCancel }: ConfirmDialogProps) {
  const headingId = useId()
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={headingId}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,.6)',
        zIndex: 300,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onCancel() }}
    >
      <div
        style={{
          background: 'var(--bg-secondary)',
          border: '1px solid var(--border-color)',
          borderRadius: 8,
          padding: '20px 24px',
          width: 320,
          maxWidth: '100%',
          boxShadow: '0 8px 32px rgba(0,0,0,.5)',
          whiteSpace: 'normal',
        }}
      >
        <p id={headingId} style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: 'var(--text-primary)' }}>
          {heading}
        </p>
        {children}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'flex-end', marginTop: 8 }}>
          <button type="button" className="btn" onClick={onCancel}>Cancel</button>
          {chip}
          {confirm}
        </div>
      </div>
    </div>
  )
}
