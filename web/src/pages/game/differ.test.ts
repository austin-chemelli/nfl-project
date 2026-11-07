import { describe, expect, it } from 'vitest'
import type { Game, StrongCall, Swing } from '../../data/contract'
import { factorLines, outcome, whatIfLine, whoText } from './differ'

const g = { home: 'BAL', away: 'JAX' } as Game
const qb = (team: string): Swing => ({
  kind: 'qb', team, text: null, why: 'status',
  assumed: { qb: 'q1', name: 'Lamar Jackson', status: 'Questionable', p_home: { student: 0.62 } },
  alternative: { qb: 'q2', name: 'Tyler Huntley', status: null, p_home: { student: 0.54 } },
})

describe('differ words', () => {
  it('reads the what-if from the swinging team\'s side', () => {
    expect(whatIfLine(g, qb('BAL'))).toBe('If Tyler Huntley starts: the Student has BAL at 54%, against 62% with Lamar Jackson.')
    expect(whatIfLine(g, qb('JAX'))).toBe('If Tyler Huntley starts: the Student has JAX at 46%, against 38% with Lamar Jackson.')
  })
  it('says nothing without both numbers', () => {
    expect(whatIfLine(g, { ...qb('BAL'), alternative: null })).toBeNull()
  })
  it('names the status when there is one', () => {
    expect(whoText({ name: 'Lamar Jackson', status: 'Questionable' })).toBe('Lamar Jackson (questionable)')
    expect(whoText({ name: 'Lamar Jackson', status: null })).toBe('Lamar Jackson')
  })
  it('grades a call in a few words', () => {
    const c = { result: 'right', closing_toward: true } as StrongCall
    expect(outcome(c)).toBe('Right · the line moved toward it')
    expect(outcome({ ...c, result: null })).toBeNull()
    expect(outcome({ ...c, result: 'wrong', closing_toward: null })).toBe('Wrong')
  })
  it('lists the other factors', () => {
    expect(factorLines([qb('BAL'), { kind: 'rest', team: 'BAL', text: 'BAL on a short week (4 days\' rest)', why: null, assumed: null, alternative: null }])).toEqual(["BAL on a short week (4 days' rest)"])
  })
})
