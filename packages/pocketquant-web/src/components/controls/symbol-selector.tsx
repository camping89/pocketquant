import { useState, useRef, useEffect } from 'react'
import { useSymbols } from '../../hooks/use-symbols'
import type { SelectedSymbol } from '../../types/market-data'

interface SymbolSelectorProps {
  value: SelectedSymbol
  onChange: (v: SelectedSymbol) => void
}

export function SymbolSelector({ value, onChange }: SymbolSelectorProps) {
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

  const filtered = symbols?.filter(
    (s) =>
      s.is_active &&
      (`${s.exchange}:${s.symbol}`.toLowerCase().includes(filter.toLowerCase()) ||
        s.name.toLowerCase().includes(filter.toLowerCase())),
  )

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(!open)}
        className="symbol-btn"
      >
        {value.exchange}:{value.symbol}
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
            {filtered?.map((s) => (
              <button
                key={`${s.exchange}:${s.symbol}`}
                className={`symbol-option ${s.exchange === value.exchange && s.symbol === value.symbol ? 'active' : ''}`}
                onClick={() => {
                  onChange({ exchange: s.exchange, symbol: s.symbol })
                  setOpen(false)
                  setFilter('')
                }}
              >
                <span className="symbol-code">{s.exchange}:{s.symbol}</span>
                <span className="symbol-name">{s.name}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
