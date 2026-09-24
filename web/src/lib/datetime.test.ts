import { describe, expect, it } from 'vitest'
import { ageColorClass } from './datetime'
import { statusVariant } from '../components/monitor/format-helpers'
import type { SyncStatus } from '../types/market-data'

const DAY_OLD = new Date(Date.now() - 86_400_000).toISOString()

describe('ageColorClass', () => {
  it('reads an old bar as stale while the market is open', () => {
    expect(ageColorClass(DAY_OLD, '1m')).toBe('age-stale')
    expect(ageColorClass(DAY_OLD, '1m', true)).toBe('age-stale')
  })

  it('reads an old bar as neutral while the market is closed', () => {
    expect(ageColorClass(DAY_OLD, '1m', false)).toBe('age-neutral')
  })
})

describe('statusVariant', () => {
  const stuck: SyncStatus = {
    symbol: 'ES1!:CME_MINI',
    interval: '1m',
    status: 'completed',
    bar_count: 10,
    last_sync_at: null,
    last_bar_at: DAY_OLD,
    error_message: null,
    is_stuck: true,
  }

  it('warns on a stuck symbol in an open market', () => {
    expect(statusVariant({ ...stuck, is_market_open: true })).toBe('warn')
  })

  it('stays neutral on a stuck symbol in a closed market', () => {
    expect(statusVariant({ ...stuck, is_market_open: false })).toBe('neutral')
  })

  it('reads a delayed but flowing feed as neutral, not synced-green', () => {
    const delayed = { ...stuck, is_stuck: false, is_delayed: true, is_market_open: true }
    expect(statusVariant(delayed)).toBe('neutral')
  })
})
