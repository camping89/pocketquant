import { describe, expect, it } from 'vitest'
import { dataLagLabel, dataLagMessage, formatLag } from './data-lag'

describe('formatLag', () => {
  it('rounds to whole minutes and never shows zero', () => {
    expect(formatLag(720)).toBe('12 min')
    expect(formatLag(20)).toBe('1 min')
  })

  it('switches to hours past sixty minutes', () => {
    expect(formatLag(3900)).toBe('1 h 5 min')
    expect(formatLag(7200)).toBe('2 h')
  })
})

describe('dataLagLabel', () => {
  it('flags a delayed or stalled feed', () => {
    expect(dataLagLabel('delayed', 720)).toBe('Delayed ~12 min')
    expect(dataLagLabel('stuck', 1800)).toBe('Stalled ~30 min')
  })

  it('shows nothing for a current, closed or unknown feed', () => {
    expect(dataLagLabel('ok', 0)).toBeNull()
    expect(dataLagLabel('closed', 0)).toBeNull()
    expect(dataLagLabel('unknown', null)).toBeNull()
  })
})

describe('dataLagMessage', () => {
  it('explains a delayed feed as working, just late', () => {
    const msg = dataLagMessage('ES1!', 'delayed', 720)
    expect(msg).toContain('ES1! data is about 12 min behind real time')
    expect(msg).toContain('delayed')
  })

  it('explains a stalled feed as not catching up', () => {
    expect(dataLagMessage('YM1!', 'stuck', 1800)).toContain('stopped catching up')
  })

  it('says nothing when the data is current', () => {
    expect(dataLagMessage('BTCUSDT', 'ok', 0)).toBeNull()
  })
})
