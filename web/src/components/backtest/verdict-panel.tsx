import { useState } from 'react'
import { useSetVerdict } from '../../hooks/use-backtest-run'

interface VerdictPanelProps {
  runId: string
  verdict: string | null | undefined
}

/** A run's conclusion, shown as read-mode prose that flips to an editor on
 *  demand. Save is optimistic (useSetVerdict); on failure the cached run reverts
 *  but the editor stays open with the text KEPT so the user can retry. */
export function VerdictPanel({ runId, verdict }: VerdictPanelProps) {
  const canonical = verdict ?? ''
  const [text, setText] = useState(canonical)
  const [editing, setEditing] = useState(false)
  // Reset when the route switches to a DIFFERENT run — not when this run's
  // verdict changes (optimistic write + revert both flow through the `verdict`
  // prop; resetting on those would clobber the user's text on a failed save).
  // Track runId via the "store info from previous render" pattern, not an effect.
  const [seenRunId, setSeenRunId] = useState(runId)
  if (seenRunId !== runId) {
    setSeenRunId(runId)
    setText(canonical)
    setEditing(false)
  }

  const mutation = useSetVerdict(runId)
  const dirty = text !== canonical

  function save() {
    mutation.mutate(text.trim() === '' ? null : text, { onSuccess: () => setEditing(false) })
  }

  function cancel() {
    setText(canonical)
    setEditing(false)
    mutation.reset()
  }

  return (
    <section className="verdict-card">
      <div className="verdict-card__head">
        <span className="verdict-card__label">Verdict</span>
        <div className="verdict-card__actions">
          {editing ? (
            <>
              <button type="button" className="btn-sm" onClick={cancel} disabled={mutation.isPending}>
                Cancel
              </button>
              <button type="button" className="btn-sm" onClick={save} disabled={!dirty || mutation.isPending}>
                {mutation.isPending ? 'Saving…' : 'Save'}
              </button>
            </>
          ) : (
            <button type="button" className="btn-sm" onClick={() => setEditing(true)}>
              {canonical ? 'Edit' : 'Add verdict'}
            </button>
          )}
        </div>
      </div>

      {editing ? (
        <>
          <textarea
            className="verdict-card__textarea"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Conclusion for this run — what worked, what killed it…"
            rows={4}
            autoFocus
          />
          <div className="verdict-card__helper">Leave empty to clear the verdict.</div>
        </>
      ) : canonical ? (
        <p className="verdict-card__body">{canonical}</p>
      ) : (
        <p className="verdict-card__empty">No verdict recorded for this run yet.</p>
      )}

      {mutation.isError && (
        <div className="verdict-card__error">
          Save failed — {(mutation.error as Error)?.message ?? 'unknown error'}. Text kept; press Save to retry.
        </div>
      )}
    </section>
  )
}
