import { describe, expect, it } from 'vitest'
import { fmtPrice } from './position-format'

describe('fmtPrice', () => {
  it('keeps 5 decimals for FX majors', () => {
    expect(fmtPrice(1.08456)).toBe('1.08456')
  })

  it('uses 3 decimals for JPY-scale prices', () => {
    expect(fmtPrice(151.234)).toBe('151.234')
  })

  it('uses 2 decimals for large prices', () => {
    expect(fmtPrice(5012.25)).toBe('5012.25')
    expect(fmtPrice(-1234.5)).toBe('-1234.50')
  })
})
