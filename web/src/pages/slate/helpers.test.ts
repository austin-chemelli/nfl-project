import { describe, expect, it } from 'vitest'
import type { CardData, GameRow, LeagueFile, Meta } from '../../data/contract'
import { gapToMarket, cardSentence, contrastLine, correct, disagreements, divergenceText, gameStatus, homeWon, neighbours, parseSort, pickOf, sideText, sortGames, stakesLine, whyLine, winnerMarketP } from './helpers'

const pick = (p: number, div: number | null = null) => ({ p_home: p, spread_home: null, status: 'preview' as const, lock_ts: null, divergence: div })
const game = (over: Partial<GameRow> = {}): GameRow => ({
  game_id: 'g', season: 2026, week: 8, kickoff_utc: '2026-10-30T00:15:00Z', away: 'CAR', home: 'GB', stadium: null, roof: null,
  neutral_site: false, away_qb: null, home_qb: null, result: null, market: null, card: null, line_move: null,
  models: { traditionalist: pick(0.7), analyst: pick(0.4), sharp: pick(0.55), student: pick(0.5) },
  ...over,
})

describe('slate helpers', () => {
  it('says when no approach has scored a game', () => {
    expect(gameStatus(game({ models: {} }))).toEqual({ status: 'none', lockTs: null })
    expect(gameStatus(game()).status).toBe('preview')
  })
  it('picks the favored side', () => {
    expect(pickOf(game(), 'traditionalist')).toMatchObject({ team: 'GB', home: true })
    expect(pickOf(game(), 'analyst')?.team).toBe('CAR')
    expect(pickOf(game(), 'analyst')?.p).toBeCloseTo(0.6)
    expect(pickOf(game(), 'nope')).toBeNull()
  })
  it('scores correctness only for finished games', () => {
    expect(correct(game(), 'analyst')).toBeNull()
    const final = game({ result: { home_score: 20, away_score: 10, margin: 10 } })
    expect(homeWon(final)).toBe(true)
    expect(correct(final, 'traditionalist')).toBe(true)
    expect(correct(final, 'analyst')).toBe(false)
    expect(homeWon(game({ result: { home_score: 10, away_score: 10, margin: 0 } }))).toBeNull()
  })
  it('ranks disagreement by spread', () => {
    const calm = game({ game_id: 'calm', models: { traditionalist: pick(0.6), analyst: pick(0.61), sharp: pick(0.6), student: pick(0.6) } })
    const top = disagreements([calm, game({ game_id: 'wild' })])
    expect(top.map((d) => d.game.game_id)).toEqual(['wild', 'calm'])
    expect(top[0]).toMatchObject({ hi: 'traditionalist', lo: 'analyst' })
    expect(top[0].spread).toBeCloseTo(0.3)
  })
  it('words', () => {
    expect(sideText(game(), 0.3)).toBe('CAR 70%')
    expect(divergenceText(0.06, game())).toBe('6 pts more on GB than the market')
    expect(divergenceText(-0.08, game())).toBe('8 pts more on CAR than the market')
  })
  it('finds neighbours', () => {
    expect(neighbours([1, 2, 3], 1)).toEqual({ prev: null, next: 2 })
    expect(neighbours([1, 2, 3], 3)).toEqual({ prev: 2, next: null })
    expect(neighbours([1, 2, 3], 9)).toEqual({ prev: null, next: null })
  })
})

const mk = (p: number) => ({ p_home: p, spread_home: null, total: null, as_of: null, source: null }) as unknown as GameRow['market']
const finalOf = (margin: number) => ({ home_score: margin > 0 ? 24 : 17, away_score: margin > 0 ? 17 : 24, margin })
const models = (a: number, s: number, t = a, st = a) => ({ traditionalist: pick(t), analyst: pick(a), sharp: pick(s), student: pick(st) })

describe('cardSentence', () => {
  it('pregame: names the approach furthest from the market', () => {
    expect(cardSentence(game({ market: mk(0.7), models: models(0.72, 0.58) }))).toBe('Sharp is 12 pts from the market on CHI'.replace('CHI', 'CAR'))
    expect(cardSentence(game({ market: mk(0.5), models: models(0.52, 0.64) }))).toBe('Sharp is 14 pts from the market on GB')
  })
  it('pregame: all agree with the market', () => {
    expect(cardSentence(game({ market: mk(0.65), models: models(0.66, 0.68) }))).toBe('All four agree with the market')
  })
  it('pregame: splits', () => {
    expect(cardSentence(game({ market: mk(0.5), models: models(0.4, 0.6, 0.6, 0.4) }))).toBe('Approaches split 2–2')
    expect(cardSentence(game({ market: mk(0.6), models: models(0.6, 0.4, 0.6, 0.6) }))).toBe('Split 3–1 GB; Sharp takes CAR')
  })
  it('pregame: unanimous against the market, and with no line', () => {
    expect(cardSentence(game({ market: mk(0.48), models: models(0.52, 0.53) }))).toBe('All four pick GB; the market leans CAR')
    expect(cardSentence(game({ market: null, models: models(0.6, 0.7) }))).toBe('All four pick GB')
    expect(cardSentence(game({ models: {} }))).toBe('Not scored yet')
  })
  it('finished: upset only outside the toss-up band', () => {
    expect(cardSentence(game({ market: mk(0.61), result: finalOf(-3), models: models(0.6, 0.6) }))).toBe('Upset: CAR won as a 39% underdog')
    expect(cardSentence(game({ market: mk(0.52), result: finalOf(-3), models: models(0.6, 0.6) }))).toBe('All four picked GB; CAR won')
  })
  it('finished: who called it', () => {
    const base = { market: mk(0.6), result: finalOf(7) }
    expect(cardSentence(game({ ...base, models: models(0.6, 0.6) }))).toBe('All four picked GB')
    expect(cardSentence(game({ ...base, models: models(0.4, 0.4, 0.6, 0.6) }))).toBe('Traditionalist and Student called it')
    expect(cardSentence(game({ ...base, models: models(0.6, 0.4, 0.6, 0.6) }))).toBe('Sharp missed it')
    expect(cardSentence(game({ ...base, result: finalOf(0), models: models(0.6, 0.6) }))).toBe('Ended in a tie')
  })
})

describe('sortGames', () => {
  const a = game({ game_id: 'a', kickoff_utc: '2026-10-30T17:00:00Z', market: mk(0.8), result: finalOf(7), models: models(0.5, 0.5) }) // favorite won
  const b = game({ game_id: 'b', kickoff_utc: '2026-10-30T18:00:00Z', market: mk(0.7), result: finalOf(-3), models: models(0.2, 0.9) }) // upset (30%), wide spread
  const c = game({ game_id: 'c', kickoff_utc: '2026-10-29T18:00:00Z', market: mk(0.6), models: models(0.6, 0.65) }) // unplayed, calm
  const d = game({ game_id: 'd', kickoff_utc: '2026-10-31T18:00:00Z', models: {} }) // nothing scored
  const ids = (xs: GameRow[]) => xs.map((g) => g.game_id)
  it('kickoff', () => expect(ids(sortGames([a, b, c, d], 'kickoff'))).toEqual(['c', 'a', 'b', 'd']))
  it('gap to market: widest first, no market or no forecast last', () => {
    // student vs market: b 0.5, a 0.3, c 0; d has neither
    expect(ids(sortGames([a, b, c, d], 'disagreement'))).toEqual(['b', 'a', 'c', 'd'])
    const noMarket = game({ game_id: 'n', kickoff_utc: '2026-10-28T18:00:00Z', models: models(0.1, 0.9) })
    expect(ids(sortGames([noMarket, a, b], 'disagreement'))).toEqual(['b', 'a', 'n'])
  })
  it('upset: lowest winner chance first, then the unplayed by kickoff', () => expect(ids(sortGames([a, b, c, d], 'upset'))).toEqual(['b', 'a', 'c', 'd']))
  it('upset: unplayed games keep kickoff order whatever the input order', () => {
    const e = game({ game_id: 'e', kickoff_utc: '2026-10-29T12:00:00Z', market: mk(0.5), models: models(0.5, 0.5) })
    expect(ids(sortGames([d, c, e, b, a], 'upset'))).toEqual(['b', 'a', 'e', 'c', 'd'])
  })
  it('spread, winner market and sort parsing', () => {
    expect(gapToMarket(b)).toBeCloseTo(0.5)
    expect(gapToMarket(d)).toBeNull()
    expect(winnerMarketP(b)).toBeCloseTo(0.3)
    expect(winnerMarketP(c)).toBeNull()
    expect(parseSort('upset')).toBe('upset')
    expect(parseSort('nope')).toBe('kickoff')
  })
})

describe('gameStatus', () => {
  const m = (status: string) => ({ ...pick(0.5), status: status as 'locked', lock_ts: status })
  const row = (models: GameRow['models']) => game({ models })
  it('reads the Student, whatever else the row carries and in whatever order', () => {
    expect(gameStatus(row({ market_baseline: m('preview'), student: m('locked') }))).toEqual({ status: 'locked', lockTs: 'locked' })
  })
  it('falls back to an approach, then a reference, never to the key order', () => {
    expect(gameStatus(row({ global: m('pregame'), elo_v0: m('backfill'), sharp: m('locked') })).status).toBe('locked')
    expect(gameStatus(row({ global: m('pregame'), elo_v0: m('backfill') })).status).toBe('backfill')
    expect(gameStatus(row({})).status).toBe('none')
  })
})

describe('whyLine', () => {
  const meta = {
    current_week: 8,
    groups: { groups: [{ id: 'form', name: 'Form', context_only: false }, { id: 'offense', name: 'Offense', context_only: false }, { id: 'rest_travel', name: 'Rest & travel', context_only: false }, { id: 'venue_weather', name: 'Venue & weather', context_only: false }, { id: 'coaching', name: 'Coaching', context_only: true }] },
  } as unknown as Meta
  const none = { home: null, away: null }
  const card = (over: Partial<CardData> = {}): CardData => ({ edges: {}, injuries: [], usual_qb: none, last_qb: none, charted_qb: none, weather_concern: null, contrast: null, ...over })
  const withCard = (c: Partial<CardData> | null, over: Partial<GameRow> = {}) => game({ roof: 'outdoors', card: c == null ? null : card(c), ...over })
  const edge = (pct: number, id = 'form') => ({ [id]: { favors: 'JAX', strength_pct: pct } })
  const out = { team: 'BAL', player: 'A Name', pos: 'WR', status: 'Out', starter: true, new: true }
  // the home side: Jordan Love is the regular and the last starter
  const usual = { usual_qb: { home: 'Jordan Love', away: null }, last_qb: { home: 'Jordan Love', away: null } }

  it('is null with no card, no pieces and no edges, or a finished game', () => {
    expect(whyLine(withCard(null), meta)).toBeNull()
    expect(whyLine(withCard({}), meta)).toBeNull()
    expect(whyLine(withCard({ injuries: [out] }, { result: { home_score: 1, away_score: 0, margin: 1 } }), meta)).toBeNull()
  })

  describe('the quarterback', () => {
    const chart = (name: string) => ({ home: name, away: null })
    const hurt = (player: string, team = 'GB') => ({ ...out, team, player, pos: 'QB' })
    it('says listed, never starts, when both sources agree', () => {
      expect(whyLine(withCard({ ...usual, charted_qb: chart('Backup Bob') }, { home_qb: 'Backup Bob' }), meta)).toBe('Backup Bob listed to start for GB (usually Jordan Love)')
    })
    it('says nothing on one source: the chart goes at kickoff, and the schedule alone is a projection', () => {
      expect(whyLine(withCard(usual, { home_qb: 'Backup Bob' }), meta)).toBeNull()
      expect(whyLine(withCard({ ...usual, charted_qb: chart('Backup Bob') }), meta)).toBeNull()
    })
    it('says so whenever the two disagree, even when one of them has the regular', () => {
      const unclear = (a: string, b: string) => `GB starter unclear: ${a} on the depth chart, ${b} on the schedule`
      expect(whyLine(withCard({ ...usual, charted_qb: chart('Backup Bob') }, { home_qb: 'Third String' }), meta)).toBe(unclear('Backup Bob', 'Third String'))
      expect(whyLine(withCard({ ...usual, charted_qb: chart('Jordan Love') }, { home_qb: 'Third String' }), meta)).toBe(unclear('Jordan Love', 'Third String'))
      expect(whyLine(withCard({ ...usual, charted_qb: chart('Backup Bob') }, { home_qb: 'Jordan Love' }), meta)).toBe(unclear('Backup Bob', 'Jordan Love'))
    })
    it('leaves the regular, and a QB already in the job, alone', () => {
      expect(whyLine(withCard({ ...usual, charted_qb: chart('Jordan Love') }, { home_qb: 'Jordan Love' }), meta)).toBeNull()
      const c = { usual_qb: { home: 'Jordan Love', away: null }, last_qb: { home: 'Backup Bob', away: null }, charted_qb: chart('Backup Bob') }
      expect(whyLine(withCard(c, { home_qb: 'Backup Bob' }), meta)).toBeNull()
    })
    it('still reports disagreement with no clear regular, but not a listed line', () => {
      expect(whyLine(withCard({ charted_qb: chart('A One') }, { home_qb: 'B Two' }), meta)).toContain('GB starter unclear')
      expect(whyLine(withCard({ charted_qb: chart('A One') }, { home_qb: 'A One' }), meta)).toBeNull()
    })
    it('only speaks for the current week', () => {
      expect(whyLine(withCard({ ...usual, charted_qb: chart('Backup Bob') }, { home_qb: 'Backup Bob', week: 9 }), meta)).toBeNull()
    })
    it('reads Jr., II and punctuation as the same player', () => {
      const c = { usual_qb: { home: 'Gardner Minshew', away: null }, last_qb: none, charted_qb: chart('Gardner Minshew II') }
      expect(whyLine(withCard(c, { home_qb: 'Gardner Minshew' }), meta)).toBeNull()
      expect(whyLine(withCard({ charted_qb: chart("D'Andre O'Neil Jr.") }, { home_qb: 'DAndre ONeil' }), meta)).toBeNull()
    })
    it('never calls a hurt player the starter: the absence says it', () => {
      expect(whyLine(withCard({ ...usual, charted_qb: chart('Backup Bob'), injuries: [hurt('Backup Bob')] }, { home_qb: 'Backup Bob' }), meta)).toBe('GB without Backup Bob (QB)')
    })
    it('falls back to the healthy name when the charted QB is hurt', () => {
      const c = { ...usual, charted_qb: chart('Backup Bob'), injuries: [{ ...hurt('Backup Bob'), new: false }] }
      expect(whyLine(withCard(c, { home_qb: 'Third String' }), meta)).toBe('Third String listed to start for GB (usually Jordan Love)')
    })
    it('only counts an injury on the same team', () => {
      expect(whyLine(withCard({ ...usual, charted_qb: chart('Backup Bob'), injuries: [{ ...hurt('Backup Bob', 'CAR'), starter: false }] }, { home_qb: 'Backup Bob' }), meta)).toBe('Backup Bob listed to start for GB (usually Jordan Love)')
    })
    it('names the regular once when a listed line already does, and lets the next absence through', () => {
      const qb = hurt('Jordan Love')
      const c = { ...usual, charted_qb: chart('Backup Bob') }
      expect(whyLine(withCard({ ...c, injuries: [qb] }, { home_qb: 'Backup Bob' }), meta)).toBe('Backup Bob listed to start for GB (usually Jordan Love)')
      expect(whyLine(withCard({ ...c, injuries: [qb, out] }, { home_qb: 'Backup Bob' }), meta)).toContain('BAL without A Name (WR)')
    })
    it('still says the regular is out when the line is an unclear one, which never names him', () => {
      const c = { ...usual, charted_qb: chart('Backup Bob'), injuries: [hurt('Jordan Love')] }
      expect(whyLine(withCard(c, { home_qb: 'Third String' }), meta)).toBe('GB starter unclear: Backup Bob on the depth chart, Third String on the schedule · GB without Jordan Love (QB)')
    })
    it('lists both teams', () => {
      const c = { usual_qb: { home: 'Jordan Love', away: 'Bryce Young' }, last_qb: { home: 'Jordan Love', away: 'Bryce Young' }, charted_qb: { home: 'Backup Bob', away: 'Other Guy' } }
      expect(whyLine(withCard(c, { home_qb: 'Backup Bob', away_qb: 'Other Guy' }), meta)).toBe('Other Guy listed to start for CAR (usually Bryce Young) · Backup Bob listed to start for GB (usually Jordan Love)')
    })
  })

  describe('absences', () => {
    it('names a starter who is newly out, or doubtful', () => {
      expect(whyLine(withCard({ injuries: [out] }), meta)).toBe('BAL without A Name (WR)')
      expect(whyLine(withCard({ injuries: [{ ...out, status: 'Doubtful' }] }), meta)).toBe("BAL's A Name doubtful")
    })
    it('skips backups and players already gone for weeks', () => {
      expect(whyLine(withCard({ injuries: [{ ...out, starter: false }] }), meta)).toBeNull()
      expect(whyLine(withCard({ injuries: [{ ...out, new: false }] }), meta)).toBeNull()
    })
  })

  describe('neutral sites', () => {
    const neutral = { neutral_site: true, stadium: 'Bernabeu' }
    it('names the stadium, before any edge', () => {
      expect(whyLine(withCard({ edges: edge(92) }, neutral), meta)).toBe('Neutral site: Bernabeu · JAX form edge, 92nd pct')
      expect(whyLine(withCard({}, { ...neutral, stadium: null }), meta)).toBe('Neutral site')
    })
    it('never calls venue an edge, or rest and travel on a neutral site', () => {
      expect(whyLine(withCard({ edges: edge(98, 'venue_weather') }), meta)).toBeNull()
      expect(whyLine(withCard({ edges: edge(93, 'rest_travel') }, neutral), meta)).toBe('Neutral site: Bernabeu')
      expect(whyLine(withCard({ edges: edge(93, 'rest_travel') }), meta)).toBe('JAX rest & travel edge, 93rd pct')
    })
  })

  describe('edges', () => {
    it('takes the strongest, wherever it sits in the file', () => {
      expect(whyLine(withCard({ edges: { ...edge(80, 'offense'), ...edge(92) } }), meta)).toContain('form edge')
      expect(whyLine(withCard({ edges: { ...edge(92), ...edge(80, 'offense') } }), meta)).toContain('form edge')
    })
    it('uses edges at 75 and above; below that it is no standout edge', () => {
      expect(whyLine(withCard({ edges: edge(75) }), meta)).toContain('edge, 75th pct')
      expect(whyLine(withCard({ edges: edge(74.9) }), meta)).toBe('No standout edge')
    })
    it('never says bigger than 100%', () => {
      expect(whyLine(withCard({ edges: edge(99.8) }), meta)).toBe('JAX form edge, 99th pct')
    })
    it('skips context-only groups', () => {
      expect(whyLine(withCard({ edges: edge(99, 'coaching') }), meta)).toBeNull()
    })
  })

  it('mentions weather only outdoors (or open) and at 0.5 or more', () => {
    expect(whyLine(withCard({ weather_concern: 0.5 }), meta)).toBe('Weather could be a factor')
    expect(whyLine(withCard({ weather_concern: 0.49 }), meta)).toBeNull()
    expect(whyLine(withCard({ weather_concern: 0.9 }, { roof: 'dome' }), meta)).toBeNull()
    expect(whyLine(withCard({ weather_concern: 0.9 }, { roof: 'closed' }), meta)).toBeNull()
    expect(whyLine(withCard({ weather_concern: 0.9 }, { roof: 'open' }), meta)).toBe('Weather could be a factor')
    expect(whyLine(withCard({ weather_concern: 0.9 }, { roof: null }), meta)).toBeNull()
  })
  it('keeps two pieces, in order', () => {
    const c = { ...usual, charted_qb: { home: 'Backup Bob', away: null }, injuries: [out], edges: edge(92), weather_concern: 0.8 }
    expect(whyLine(withCard(c, { home_qb: 'Backup Bob' }), meta)).toBe('Backup Bob listed to start for GB (usually Jordan Love) · BAL without A Name (WR)')
    expect(whyLine(withCard({ ...c, injuries: [] }, { home_qb: 'Backup Bob' }), meta)).toBe('Backup Bob listed to start for GB (usually Jordan Love) · JAX form edge, 92nd pct')
    expect(whyLine(withCard({ edges: edge(92), weather_concern: 0.8 }), meta)).toBe('JAX form edge, 92nd pct · Weather could be a factor')
  })
})

describe('contrastLine', () => {
  const contrast = { offense: 'JAX', defense: 'BAL', off_label: 'pass-heavy', def_label: 'blitz-heavy', off_rank: 3, def_rank: 1 }
  const q = { home: null, away: null }
  const c = (x: typeof contrast | null) => ({ edges: {}, injuries: [], usual_qb: q, last_qb: q, charted_qb: q, weather_concern: null, contrast: x })
  it('reads most for rank 1 and the ordinal otherwise', () => {
    expect(contrastLine(game({ card: c(contrast) }))).toBe("The league's 3rd-most pass-heavy offense (JAX) faces its most blitz-heavy defense (BAL)")
    expect(contrastLine(game({ card: c({ ...contrast, off_rank: 1, def_rank: 2 }) }))).toBe("The league's most pass-heavy offense (JAX) faces its 2nd-most blitz-heavy defense (BAL)")
  })
  it('is null on a finished game, without a contrast or without a card', () => {
    expect(contrastLine(game({ card: c(contrast), result: { home_score: 1, away_score: 0, margin: 1 } }))).toBeNull()
    expect(contrastLine(game({ card: c(null) }))).toBeNull()
    expect(contrastLine(game())).toBeNull()
  })
})

describe('stakesLine', () => {
  const league = (swings: { team: string; if_home_win: number; if_away_win: number }[], runs: [number, number] = [5000, 5000]) =>
    ({
      odds: { student: { sources: {}, teams: { CHI: { playoffs: 0.55 }, BUF: { playoffs: 0.4 } } }, market: { sources: {}, teams: {} } },
      games: [{ game_id: 'g', week: 9, home: 'MIN', away: 'CHI', swings, n_home_wins: runs[0], n_away_wins: runs[1] }],
    }) as unknown as LeagueFile
  const chi = (up: number, down: number) => [{ team: 'CHI', if_home_win: down, if_away_win: up }]

  it('shows the biggest swing on the side of the team', () => {
    expect(stakesLine({ game_id: 'g' }, league(chi(0.8, 0.5)))).toBe('Playoff stakes: CHI 55% → 80% with a win.')
  })
  it('shows nothing at 7.9 points and the line at 8', () => {
    expect(stakesLine({ game_id: 'g' }, league(chi(0.629, 0.55)))).toBeNull()
    expect(stakesLine({ game_id: 'g' }, league(chi(0.63, 0.55)))).toBe('Playoff stakes: CHI 55% → 63% with a win.')
    expect(stakesLine({ game_id: 'g' }, league(chi(0.8, 0.72)))).toBe('Playoff stakes: CHI 55% → 80% with a win.')
  })
  it('picks the team with the largest swing', () => {
    const sw = [...chi(0.65, 0.5), { team: 'BUF', if_home_win: 0.7, if_away_win: 0.2 }]
    expect(stakesLine({ game_id: 'g' }, league(sw))).toBe('Playoff stakes: BUF 40% → 70% if MIN wins.')
  })
  it('needs 1,000 runs on both branches', () => {
    expect(stakesLine({ game_id: 'g' }, league(chi(0.8, 0.5), [1000, 1000]))).not.toBeNull()
    expect(stakesLine({ game_id: 'g' }, league(chi(0.8, 0.5), [999, 5000]))).toBeNull()
    expect(stakesLine({ game_id: 'g' }, league(chi(0.8, 0.5), [5000, 999]))).toBeNull()
  })
  it('is null without a file or without the game', () => {
    expect(stakesLine({ game_id: 'g' }, undefined)).toBeNull()
    expect(stakesLine({ game_id: 'g' }, null)).toBeNull()
    expect(stakesLine({ game_id: 'other' }, league(chi(0.8, 0.5)))).toBeNull()
  })
})
