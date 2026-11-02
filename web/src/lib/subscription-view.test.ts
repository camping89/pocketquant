import { describe, expect, it } from 'vitest'
import { ApiError } from '../api/api-client'
import type {
  SnapshotEntry,
  SubscriptionOrder,
  SubscriptionPosition,
} from '../api/strategy-api'
import type { StrategyTrade } from '../hooks/use-strategy-trades'
import { formatPrice } from './number-format'
import {
  decisionText,
  errorText,
  manualActionText,
  parameterRows,
  parseParameters,
  pendingText,
  positionText,
  timeline,
} from './subscription-view'

const LONG: SubscriptionPosition = {
  direction: 'LONG',
  quantity: 0.1,
  entry_price: 71000,
  sl_price: 70000,
  tp_price: 73000,
  unrealized_pnl: 12.5,
}

function entry(over: Partial<SnapshotEntry> = {}): SnapshotEntry {
  return {
    bar_start: '2026-11-01T10:00:00+00:00',
    interval: '1h',
    readings: [],
    decision: { action: 'hold', reason: 'position open' },
    outcome: 'no_signal',
    pending: null,
    ...over,
  }
}

function order(over: Partial<SubscriptionOrder> = {}): SubscriptionOrder {
  return {
    id: 'o1',
    side: 'buy',
    order_type: 'stop_market',
    status: 'pending',
    quantity: 0.1,
    price: null,
    stop_price: 71250,
    sl_price: 70000,
    tp_price: null,
    filled_price: null,
    created_at: '2026-11-01T09:00:00+00:00',
    updated_at: '2026-11-01T09:00:00+00:00',
    ...over,
  }
}

const TRADE: StrategyTrade = {
  id: 't1',
  direction: 'SHORT',
  entry_price: 72000,
  exit_price: 71500,
  entry_time: '2026-11-01T08:00:00+00:00',
  exit_time: '2026-11-01T09:30:00+00:00',
  pnl: 50,
  quantity: 0.1,
}

const AT = '2026-11-01T10:00:00+00:00'

describe('positionText', () => {
  it('shows a dash with no position', () => {
    expect(positionText(null)).toBe('-')
  })

  it('shows direction, SL and TP', () => {
    const text = positionText(LONG)
    expect(text).toContain('LONG')
    expect(text).toContain('SL ')
    expect(text).toContain('TP ')
  })

  it('leaves out a missing TP', () => {
    expect(positionText({ ...LONG, tp_price: null })).not.toContain('TP')
  })
})

describe('pendingText', () => {
  it('shows a dash with no pending order', () => {
    expect(pendingText(null)).toBe('-')
  })

  it('shows the side and stop price', () => {
    const text = pendingText({ side: 'buy', price: 71250 })
    expect(text.startsWith('BUY STOP @ ')).toBe(true)
    expect(text).toContain(formatPrice(71250))
  })
})

describe('decisionText', () => {
  it('shows a dash with no entry', () => {
    expect(decisionText(null)).toBe('-')
  })

  it('shows action and reason without a no_signal outcome', () => {
    expect(decisionText(entry())).toBe('hold - position open')
  })

  it('appends every other outcome', () => {
    for (const outcome of [
      'skipped:stale',
      'sent',
      'skipped:stop_unchanged',
      'skipped:nothing_open',
      'rejected:close_failed',
      'accepted',
    ]) {
      expect(decisionText(entry({ outcome }))).toBe(`hold - position open (${outcome})`)
    }
  })

  it('renders a manual-action record', () => {
    expect(decisionText(entry({ interval: null, outcome: 'rejected:close_failed' }))).toBe(
      'manual action (rejected:close_failed)',
    )
  })
})

describe('manualActionText', () => {
  it('is empty with no action and no outcome', () => {
    expect(manualActionText(null, null)).toBe('')
  })

  it('shows a queued action', () => {
    expect(manualActionText('close', null)).toBe(
      'close requested - runs when the trader holds the lease',
    )
  })

  it('shows an accepted outcome', () => {
    expect(manualActionText(null, { action: 'cancel', outcome: 'accepted', at: AT })).toBe(
      'cancel accepted',
    )
  })

  it('invites a retry after a rejection', () => {
    expect(
      manualActionText(null, { action: 'close', outcome: 'rejected:MARKET_SESSION_CLOSED', at: AT }),
    ).toBe('close rejected:MARKET_SESSION_CLOSED - press again to retry')
  })
})

describe('parameterRows', () => {
  it('lists defaults first, then extra keys', () => {
    expect(parameterRows({ a: 1, b: 'x' }, { b: 'y', c: 2 })).toEqual([
      { key: 'a', def: 1, value: 1, extra: false },
      { key: 'b', def: 'x', value: 'y', extra: false },
      { key: 'c', def: undefined, value: 2, extra: true },
    ])
  })
})

describe('parseParameters', () => {
  it('reads empty text as no parameters', () => {
    expect(parseParameters('')).toEqual({ value: {} })
  })

  it('reads a JSON object', () => {
    expect(parseParameters('{"a":1}')).toEqual({ value: { a: 1 } })
  })

  it('rejects a non-object and broken JSON', () => {
    for (const text of ['[1]', '{']) {
      expect(typeof (parseParameters(text) as { error?: string }).error).toBe('string')
    }
  })
})

describe('timeline', () => {
  it('merges orders and trades newest first', () => {
    const items = timeline(
      [order(), order({ id: 'o2', order_type: 'market', updated_at: '2026-11-01T10:00:00+00:00' })],
      [TRADE],
    )
    expect(items.map((i) => i.at)).toEqual([
      '2026-11-01T10:00:00+00:00',
      '2026-11-01T09:30:00+00:00',
      '2026-11-01T09:00:00+00:00',
    ])
  })

  it('shows a stop order with its stop price', () => {
    const [item] = timeline([order()], [])
    expect(item.text).toContain('STOP')
    expect(item.text).toContain(formatPrice(71250))
  })

  it('shows a closed trade', () => {
    const [item] = timeline([], [TRADE])
    expect(item.text).toContain('closed @')
  })
})

describe('errorText', () => {
  it('prefixes the backend code', () => {
    expect(errorText(new ApiError('busy', 409, 'ACTION_PENDING'))).toBe('ACTION_PENDING: busy')
  })

  it('asks for the admin token on a 401', () => {
    expect(errorText(new ApiError('x', 401))).toBe(
      'Admin token required: reload the page and enter it.',
    )
  })

  it('falls back to the message', () => {
    expect(errorText(new Error('x'))).toBe('x')
  })
})
