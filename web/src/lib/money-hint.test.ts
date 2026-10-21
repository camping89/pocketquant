import { describe, expect, it } from 'vitest'
import { moneyHint, type Broker, type MoneyAction } from './money-hint'

const BROKERS: Broker[] = ['paper', 'exness']
const ACTIONS: MoneyAction[] = ['start', 'stop', 'delete', 'pause', 'resume']

describe('moneyHint', () => {
  it('gives every action a non-empty title on both brokers', () => {
    for (const broker of BROKERS) {
      for (const action of ACTIONS) {
        expect(moneyHint(broker, action).title).toMatch(/\S/)
      }
    }
  })

  it('marks every exness action as real money', () => {
    for (const action of ACTIONS) {
      expect(moneyHint('exness', action)).toMatchObject({ real: true, chip: 'Real money' })
    }
  })

  it('marks pause and resume as real money even when called with paper', () => {
    expect(moneyHint('paper', 'pause').real).toBe(true)
    expect(moneyHint('paper', 'resume').real).toBe(true)
  })

  it('marks paper start, stop and delete as paper only', () => {
    for (const action of ['start', 'stop', 'delete'] as const) {
      expect(moneyHint('paper', action)).toEqual({
        real: false,
        chip: 'Paper',
        title: 'Paper only, no real orders',
      })
    }
  })
})
