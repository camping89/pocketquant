import { useState, useRef, useEffect } from 'react'
import { useSymbols } from '../../hooks/use-symbols'
import { parseSymbol } from '../../lib/symbol-format'

interface SymbolSelectorProps {
  /** Composite symbol string: "{CODE}:{EXCHANGE}" e.g. "BTCUSDT:BINANCE" */
  value: string
  onChange: (v: string) => void
  /** Shown when value is empty — avoids a blank button before a symbol is picked. */
  placeholder?: string
}

export function SymbolSelector({ value, onChange, placeholder = 'Select symbol…' }: SymbolSelectorProps) {
  const { data: symbols } = useSymbols()
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const lowerFilter = filter.toLowerCase()
  const filtered = symbols?.filter((s) => {
    if (!s.is_active) return false
    // s.symbol is now a composite string from the API
    const { code } = parseSymbol(s.symbol)
    return (
      s.symbol.toLowerCase().includes(lowerFilter) ||
      code.toLowerCase().includes(lowerFilter) ||
      s.name.toLowerCase().includes(lowerFilter)
    )
  })

  const { code: selectedCode, exchange: selectedExchange } = parseSymbol(value)

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button onClick={() => setOpen(!open)} className="symbol-btn">
        {selectedCode ? (
          <>
            <span className="symbol-code">{selectedCode}</span>
            {selectedExchange && <span className="exchange-badge">{selectedExchange}</span>}
          </>
        ) : (
          <span className="symbol-placeholder">{placeholder}</span>
        )}
      </button>
      {open && (
        <div className="symbol-dropdown">
          <input
            autoFocus
            placeholder="Search..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="symbol-search"
          />
          <div className="symbol-list">
            {filtered?.map((s) => {
              const { code, exchange } = parseSymbol(s.symbol)
              return (
                <button
                  key={s.symbol}
                  className={`symbol-option ${s.symbol === value ? 'active' : ''}`}
                  onClick={() => {
                    onChange(s.symbol)
                    setOpen(false)
                    setFilter('')
                  }}
                >
                  <span className="symbol-code">{code}</span>
                  {exchange && <span className="exchange-badge">{exchange}</span>}
                  <span className="symbol-name">{s.name}</span>
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
