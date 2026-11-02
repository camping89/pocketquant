import { useState } from 'react'
import { parameterRows, parseParameters } from '../../lib/subscription-view'

interface ParamsEditorProps {
  defaults: Record<string, unknown>
  // The JSON text is the single state; the table reads and writes it.
  text: string
  onChange: (text: string) => void
}

function show(v: unknown): string {
  if (v === undefined) return ''
  return typeof v === 'string' ? v : JSON.stringify(v)
}

// The number and boolean rules follow the declared default; anything else stays a string.
function coerce(input: string, def: unknown): unknown {
  if (typeof def === 'number' && input.trim() !== '' && Number.isFinite(Number(input))) {
    return Number(input)
  }
  if (typeof def === 'boolean') return input === 'true'
  return input
}

const cellStyle: React.CSSProperties = {
  padding: '3px 6px',
  borderBottom: '1px solid var(--border-color)',
  fontSize: 12,
  textAlign: 'left',
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '3px 6px',
  background: 'var(--bg-primary)',
  border: '1px solid var(--border-color)',
  borderRadius: 4,
  color: 'var(--text-primary)',
  fontSize: 12,
}

export function ParamsEditor({ defaults, text, onChange }: ParamsEditorProps) {
  const [raw, setRaw] = useState(false)
  const parsed = parseParameters(text)
  const values = 'value' in parsed ? parsed.value : null
  const rows = values ? parameterRows(defaults, values) : []

  function write(key: string, v: unknown) {
    onChange(JSON.stringify({ ...(values ?? {}), [key]: v }, null, 2))
  }

  return (
    <div>
      {Object.keys(defaults).length === 0 && (
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
          This strategy declares no parameters.
        </div>
      )}

      {!raw && rows.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 4 }}>
          <thead>
            <tr>
              <th style={cellStyle}>Key</th>
              <th style={cellStyle}>Default</th>
              <th style={cellStyle}>Value</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key}>
                <td style={{ ...cellStyle, fontFamily: 'monospace' }} title={row.extra ? 'not declared by the strategy' : undefined}>
                  {row.key}{row.extra ? ' *' : ''}
                </td>
                <td style={{ ...cellStyle, color: 'var(--text-secondary)' }}>{show(row.def)}</td>
                <td style={cellStyle}>
                  {typeof row.def === 'boolean' ? (
                    <select
                      style={inputStyle}
                      value={String(row.value === true)}
                      onChange={(e) => write(row.key, coerce(e.target.value, row.def))}
                    >
                      <option value="true">true</option>
                      <option value="false">false</option>
                    </select>
                  ) : (
                    // Uncontrolled and committed on blur, so "1." or "-" can be typed; the key
                    // remounts the cell when the text changes elsewhere.
                    <input
                      key={show(row.value)}
                      style={inputStyle}
                      defaultValue={show(row.value)}
                      onBlur={(e) => {
                        if (e.target.value !== show(row.value)) write(row.key, coerce(e.target.value, row.def))
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault()
                          e.currentTarget.blur()
                        }
                      }}
                    />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {(raw || !values) && (
        <textarea
          style={{ ...inputStyle, fontFamily: 'monospace', minHeight: 80, resize: 'vertical' }}
          placeholder="{}"
          value={text}
          onChange={(e) => onChange(e.target.value)}
        />
      )}

      {'error' in parsed && (
        <div style={{ color: '#ef5350', fontSize: 12, marginTop: 4 }}>{parsed.error}</div>
      )}

      <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>
        <input type="checkbox" checked={raw} onChange={(e) => setRaw(e.target.checked)} />
        Edit as raw JSON
      </label>
    </div>
  )
}
