// Real-money hints for action buttons. One table so every button, dialog and
// chip says the same thing about whether an action touches real money.

export type Broker = 'paper' | 'exness'
export type MoneyAction = 'start' | 'stop' | 'delete' | 'pause' | 'resume'

export interface MoneyHint {
  real: boolean
  chip: 'Real money' | 'Paper'
  title: string
}

const REAL_TITLES: Record<MoneyAction, string> = {
  pause: 'Real money: blocks new entries; open positions and SL/TP unchanged',
  resume: 'Real money: re-enables real-money entries',
  start: 'Real money: starts real orders on Exness',
  stop: 'Real money: stops new signals; open position stays with venue SL/TP',
  delete: 'Real money: deletes this Exness subscription (stop it first)',
}

const PAPER_TITLE = 'Paper only, no real orders'

/** Pause and resume act on the Exness account, so they are real money whatever the broker. */
export function moneyHint(broker: Broker, action: MoneyAction): MoneyHint {
  const real = broker === 'exness' || action === 'pause' || action === 'resume'
  return real
    ? { real, chip: 'Real money', title: REAL_TITLES[action] }
    : { real, chip: 'Paper', title: PAPER_TITLE }
}
