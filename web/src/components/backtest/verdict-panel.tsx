import { useState } from 'react'
import { useSetVerdict } from '../../hooks/use-backtest-run'

interface VerdictPanelProps {
  runId: string
  verdict: string | null | undefined
}

/** Edit a run's conclusion. Save is optimistic (useSetVerdict); on failure the
 *  cached run reverts but the textarea text is KEPT here so the user can retry. */
export function VerdictPanel({ runId, verdict }: VerdictPanelProps) {
  const canonical = verdict ?? ''
  const [text, setText] = useState(canonical)
  // Reset the textarea only when the route switches to a DIFFERENT run — not when
  // this run's verdict changes (optimistic write + revert both flow through the
  // `verdict` prop; resetting on those would clobber the user's text on a failed
  // save, the exact case validation Q6 says must keep the text). Track runId via
  // the "store info from previous render" pattern instead of an effect.
  const [seenRunId, setSeenRunId] = useState(runId)
  if (seenRunId !== runId) {
    setSeenRunId(runId)
    setText(canonical)
  }

  const mutation = useSetVerdict(runId)
  const dirty = text !== canonical

  function save() {
    mutation.mutate(text.trim() === '' ? null : text)
  }

  return (
    <section style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)', borderRadius: 8, padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: 0.4 }}>
          Verdict
        </span>
        <button type="button" className="btn-sm" onClick={save} disabled={!dirty || mutation.isPending}>
          {mutation.isPending ? 'Saving…' : 'Save'}
        </button>
      </div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Conclusion for this run — what worked, what killed it…"
        rows={2}
        style={{ width: '100%', resize: 'vertical', background: 'var(--bg-primary)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', borderRadius: 4, padding: '6px 8px', fontSize: 13, fontFamily: 'inherit' }}
      />
      {mutation.isError && (
        <div style={{ fontSize: 12, color: 'var(--down-color)' }}>
          Save failed — {(mutation.error as Error)?.message ?? 'unknown error'}. Text kept; press Save to retry.
        </div>
      )}
    </section>
  )
}
