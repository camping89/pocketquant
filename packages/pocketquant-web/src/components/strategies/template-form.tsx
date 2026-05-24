/**
 * Dynamic form rendered from a strategy template's param schema.
 * Each entry in `params` is a { key, label?, type?, value } descriptor.
 * Falls back to a plain <input> per param when schema is minimal.
 */

export interface TemplateParam {
  key: string
  label?: string
  type?: 'number' | 'string' | 'boolean'
  value: string | number | boolean
}

interface TemplateFormProps {
  params: TemplateParam[]
  onChange: (key: string, value: string | number | boolean) => void
  disabled?: boolean
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 11,
  color: 'var(--text-secondary)',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  marginBottom: 4,
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '5px 9px',
  background: 'var(--bg-primary)',
  border: '1px solid var(--border-color)',
  borderRadius: 4,
  color: 'var(--text-primary)',
  fontSize: 13,
}

export function TemplateForm({ params, onChange, disabled = false }: TemplateFormProps) {
  if (params.length === 0) {
    return (
      <div style={{ fontSize: 12, color: 'var(--text-secondary)', padding: '8px 0' }}>
        No configurable parameters.
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {params.map((param) => {
        const fieldLabel = param.label ?? param.key
        const type = param.type ?? (typeof param.value === 'number' ? 'number' : 'string')

        if (type === 'boolean') {
          return (
            <label key={param.key} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: disabled ? 'default' : 'pointer' }}>
              <input
                type="checkbox"
                checked={param.value as boolean}
                disabled={disabled}
                onChange={(e) => onChange(param.key, e.target.checked)}
              />
              <span style={{ fontSize: 13, color: 'var(--text-primary)' }}>{fieldLabel}</span>
            </label>
          )
        }

        return (
          <div key={param.key}>
            <label style={labelStyle}>{fieldLabel}</label>
            <input
              style={{ ...inputStyle, opacity: disabled ? 0.6 : 1 }}
              type={type === 'number' ? 'number' : 'text'}
              value={String(param.value)}
              disabled={disabled}
              onChange={(e) => {
                const raw = e.target.value
                onChange(param.key, type === 'number' ? (parseFloat(raw) || 0) : raw)
              }}
            />
          </div>
        )
      })}
    </div>
  )
}
