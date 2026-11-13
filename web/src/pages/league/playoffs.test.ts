import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { LeagueFile, type LeagueGame } from '../../data/contract'
import { barWidth, divisionTables, fmtProb, gamesByLeverage, LATER_GAMES, marketNote, nextWeek, oddsRows, parseConf, parseView, sourcesText, swingLines, swingText, winsRange } from './playoffs'

const file = LeagueFile.parse(JSON.parse(fs.readFileSync(path.resolve(import.meta.dirname, '../../test/fixtures/site/league.json'), 'utf8')))
const game = (over: Partial<LeagueGame> = {}): LeagueGame => LeagueFile.shape.games.unwrap().element.parse({ game_id: 'g', week: 9, home: 'MIN', away: 'BUF', n_home_wins: 5000, n_away_wins: 5000, ...over })

describe('fmtProb', () => {
  it('never says 0% or 100%', () => {
    expect(fmtProb(0)).toBe('<0.1%')
    expect(fmtProb(0.0009)).toBe('<0.1%')
    expect(fmtProb(1)).toBe('>99.9%')
    expect(fmtProb(0.9995)).toBe('>99.9%')
  })
  it('keeps a decimal near the ends so rounding can not reach 0 or 100', () => {
    expect(fmtProb(0.001)).toBe('0.1%')
    expect(fmtProb(0.0049)).toBe('0.5%')
    expect(fmtProb(0.996)).toBe('99.6%')
    expect(fmtProb(0.55)).toBe('55%')
    expect(fmtProb(0.5)).toBe('50%')
  })
  it('is a dash for no value', () => expect(fmtProb(null)).toBe('–'))
  it('never prints a bare 0% or 100% for any value on a fine grid', () => {
    for (let i = 0; i <= 10000; i++) expect(fmtProb(i / 10000)).not.toMatch(/(^|[^.\d])(0|100)%/)
  })
  it('keeps bar widths visible and under full', () => {
    expect(barWidth(0)).toBe('0.5%')
    expect(barWidth(1)).toBe('99.9%')
  })
})

describe('params', () => {
  it('fall back to AFC and the market', () => {
    expect(parseConf(null)).toBe('AFC')
    expect(parseConf('NFC')).toBe('NFC')
    expect(parseConf('x')).toBe('AFC')
    expect(parseView('market')).toBe('market')
    expect(parseView('x')).toBe('market')
    expect(parseView('student')).toBe('student')
  })
})

describe('oddsRows', () => {
  it('lists a conference sorted by P(playoffs) for the chosen variant', () => {
    for (const view of ['student', 'market'] as const) {
      const rows = oddsRows(file, 'NFC', view)
      expect(rows).toHaveLength(16)
      expect(rows.every((r) => r.team.conf === 'NFC')).toBe(true)
      const ps = rows.map((r) => r.odds.playoffs)
      expect(ps).toEqual([...ps].sort((a, b) => b - a))
      expect(rows[0].odds).toBe(file.odds[view].teams[rows[0].team.team])
    }
  })
  it('skips a team the variant lacks', () => {
    const f = structuredClone(file)
    delete f.odds.market.teams[f.teams[0].team]
    expect(oddsRows(f, f.teams[0].conf as 'AFC' | 'NFC', 'market')).toHaveLength(15)
  })
})

describe('text', () => {
  it('writes wins and source counts', () => {
    expect(winsRange({ lo: 9, hi: 13 })).toBe('9–13')
    expect(winsRange({ lo: 9, hi: 9 })).toBe('9')
    expect(sourcesText({ sources: { locked: 14, scored: 137 } })).toBe('14 from its locked picks, 137 scored fresh at the last build')
    expect(sourcesText({ sources: { line: 15, other: 2 } })).toBe('15 from the betting line, 2 other')
  })
})

describe('swings', () => {
  const f = { odds: { market: { sources: {}, teams: { CHI: { playoffs: 0.55 }, BUF: { playoffs: 0.3 } } } } } as unknown as LeagueFile
  const g = { home: 'MIN', away: 'BUF' }
  it('reads the winning branch for the team in the game', () => {
    expect(swingText(g, { team: 'BUF', if_home_win: 0.2, if_away_win: 0.5 }, f)).toBe('BUF 30% → 50% with a win')
    expect(swingText({ home: 'BUF', away: 'MIN' }, { team: 'BUF', if_home_win: 0.5, if_away_win: 0.2 }, f)).toBe('BUF 30% → 50% with a win')
  })
  it('names the side that helps a team outside the game', () => {
    expect(swingText(g, { team: 'CHI', if_home_win: 0.8, if_away_win: 0.5 }, f)).toBe('CHI 55% → 80% if MIN wins')
    expect(swingText(g, { team: 'CHI', if_home_win: 0.5, if_away_win: 0.8 }, f)).toBe('CHI 55% → 80% if BUF wins')
  })
  it('skips a team whose own win hurts it, and a team with no odds', () => {
    expect(swingText(g, { team: 'BUF', if_home_win: 0.5, if_away_win: 0.2 }, f)).toBeNull()
    expect(swingText(g, { team: 'ZZZ', if_home_win: 0.8, if_away_win: 0.5 }, f)).toBeNull()
  })
  it('orders by size and drops branches with too few runs', () => {
    const lg = game({ swings: [{ team: 'BUF', if_home_win: 0.2, if_away_win: 0.4 }, { team: 'CHI', if_home_win: 0.9, if_away_win: 0.5 }] })
    expect(swingLines(lg, f)).toEqual(['CHI 55% → 90% if MIN wins', 'BUF 30% → 40% with a win'])
    expect(swingLines({ ...lg, n_away_wins: 999 }, f)).toEqual([])
  })
  it('has no lines for a game without swings', () => expect(swingLines(game(), f)).toEqual([]))
})

describe('gamesByLeverage', () => {
  it('puts the earliest week first, each part by leverage', () => {
    const { next, rest, week } = gamesByLeverage(file.games, 0)
    expect(week).toBe(nextWeek(file.games, 0))
    expect(next.every((g) => g.week === week)).toBe(true)
    expect(next.map((g) => g.leverage_total)).toEqual(next.map((g) => g.leverage_total).sort((a, b) => b - a))
    expect(rest.every((g) => g.week > week!)).toBe(true)
    expect(next.length + rest.length).toBe(next.length + Math.min(LATER_GAMES, file.games.length - next.length))
    const lev = rest.map((g) => g.leverage_total)
    expect(lev).toEqual([...lev].sort((a, b) => b - a)) // the biggest later games, not the soonest
  })
  it('drops games that have kicked off, even with no score yet', () => {
    const first = Math.min(...file.games.map((g) => Date.parse(g.kickoff!)))
    const { next, rest } = gamesByLeverage(file.games, first)
    expect([...next, ...rest].every((g) => Date.parse(g.kickoff!) > first)).toBe(true)
  })
  it('notes the estimate only while some games lack a line', () => {
    expect(marketNote({ sources: { line: 29, ratings: 122 } })).toContain('Only 29 of the 151 games')
    expect(marketNote({ sources: { line: 151 } })).toBeNull()
    expect(marketNote({ sources: { ratings: 136 } })).toContain('None of the 136 games left has a betting line')
  })
  it('handles no games', () => expect(gamesByLeverage([], 0)).toEqual({ week: null, next: [], rest: [] }))
})

describe('divisionTables', () => {
  it('gives four divisions of four per conference, leader first', () => {
    for (const conf of ['AFC', 'NFC'] as const) {
      const t = divisionTables(file.teams, conf)
      expect(t).toHaveLength(4)
      for (const d of t) {
        expect(d.teams).toHaveLength(4)
        expect(d.teams.map((x) => x.div_rank)).toEqual([1, 2, 3, 4])
      }
    }
  })
})
