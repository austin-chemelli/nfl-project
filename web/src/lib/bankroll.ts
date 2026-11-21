/** The visitor's bankroll in dollars, kept in this browser only (null until they type one). */
import { createStore } from './browserStore'

export const BANKROLL_KEY = 'nfl-bankroll-v1'

const store = createStore<number | null>(BANKROLL_KEY, null, (raw) => (typeof raw === 'number' && Number.isFinite(raw) && raw > 0 ? raw : null))

export const useBankroll = store.use
export const getBankroll = store.get
export const setBankroll = store.set
export const resetBankrollCache = store.reset

/** Dollars to stake: `pct` (0.01 = 1%) of the bankroll, rounded to the dollar, at least $1. Null without a bankroll. */
export function stakeFor(bankroll: number | null, pct: number): number | null {
  if (bankroll == null || bankroll <= 0) return null
  return Math.max(1, Math.round(bankroll * pct))
}
