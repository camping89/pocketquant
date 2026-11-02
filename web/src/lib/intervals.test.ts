import { describe, expect, it } from 'vitest'
import { configLabel, sortIntervals } from './intervals'

describe('sortIntervals', () => {
  it('orders intervals from lowest to highest', () => {
    expect(sortIntervals(['4h', '15m', '1h'])).toEqual(['15m', '1h', '4h'])
    expect(sortIntervals(['1w', '1d'])).toEqual(['1d', '1w'])
  })

  it('does not mutate the input', () => {
    const input = ['4h', '15m', '1h']
    sortIntervals(input)
    expect(input).toEqual(['4h', '15m', '1h'])
  })
})

describe('configLabel', () => {
  it('joins intervals and key-sorted parameters', () => {
    expect(configLabel(['15m', '1h', '4h'], undefined, { exit_mode: 'strategy', entry_type: 'stop' }))
      .toBe('15m 1h 4h · entry_type=stop exit_mode=strategy')
  })

  it('falls back to the single interval when intervals are missing', () => {
    expect(configLabel(undefined, '1m', {})).toBe('1m')
  })

  it('omits the parameter part when parameters are missing', () => {
    expect(configLabel(['1h'], undefined, undefined)).toBe('1h')
  })
})
