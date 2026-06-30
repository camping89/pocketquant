import { describe, expect, it } from 'vitest'
import { formatPrice, formatQty } from './number-format'

describe('formatQty', () => {
  it('keeps magnitude for tiny crypto sizes without float noise', () => {
    expect(formatQty(0.009343299644197806)).toBe('0.0093432996')
  })

  it('keeps very small magnitudes', () => {
    expect(formatQty(0.00000123)).toBe('0.00000123')
  })

  // toPrecision(8) tips into exponential below ~1e-7 — accepted: real crypto
  // order sizes never reach this magnitude.
  it('falls back to exponential at the precision boundary', () => {
    expect(formatQty(1e-8)).toBe('1e-8')
  })

  it('passes large integers through unchanged', () => {
    expect(formatQty(5406)).toBe('5406')
  })

  it('renders zero as plain 0', () => {
    expect(formatQty(0)).toBe('0')
  })

  it('returns placeholder for null/undefined/NaN', () => {
    expect(formatQty(null)).toBe('—')
    expect(formatQty(undefined)).toBe('—')
    expect(formatQty(NaN)).toBe('—')
  })
})

describe('formatPrice', () => {
  it('adds thousands separator with 2 decimals', () => {
    expect(formatPrice(109169.1414)).toBe('109,169.14')
  })

  it('strips float noise tail', () => {
    expect(formatPrice(109169.14140000001)).toBe('109,169.14')
  })

  it('pads to 2 decimals', () => {
    expect(formatPrice(5)).toBe('5.00')
  })

  it('returns placeholder for null/undefined/NaN', () => {
    expect(formatPrice(null)).toBe('—')
    expect(formatPrice(undefined)).toBe('—')
    expect(formatPrice(NaN)).toBe('—')
  })
})
