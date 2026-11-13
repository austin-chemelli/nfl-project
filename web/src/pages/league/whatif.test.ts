import { describe, expect, it } from 'vitest'
import type { LeagueFile, LeagueGame } from '../../data/contract'
import { decide, gamesByWeek, movers, parseScenario, picksInPlay, toggle, winners, writeScenario } from './whatif'

const g = (id: string, week: number, p: number, kickoff: string): LeagueGame =>
  ({ game_id: id, week, kickoff, home: id.split('_')[3], away: id.split('_')[2], p_student: p, p_market: 1 - p }) as LeagueGame
const file = { games: [g('2026_11_BUF_KC', 11, 0.6, '2026-11-22T21:25:00Z'), g('2026_11_NYJ_MIA', 11, 0.4, '2026-11-22T18:00:00Z'), g('2026_12_KC_DEN', 12, 0.7, '2026-11-29T18:00:00Z')] } as LeagueFile
const at = '2026-11-13T00:00:00Z'

describe('what-if scenario', () => {
  it('reads and writes the link, leaving defaults out', () => {
    const s = parseScenario(new URLSearchParams('whatif=1&d=2026_11_BUF_KC:BUF,2026_12_KC_DEN:-&fav=1&mypicks=0&conf=NFC'))
    expect(s).toEqual({ on: true, decisions: new Map([['2026_11_BUF_KC', 'BUF'], ['2026_12_KC_DEN', '-']]), fav: true, usePicks: false })
    const back = writeScenario(new URLSearchParams('conf=NFC'), s)
    expect(parseScenario(back)).toEqual(s)
    expect(back.get('conf')).toBe('NFC')
    expect(writeScenario(back, { ...s, on: false }).toString()).toBe('conf=NFC')
  })

  it('the link beats your pick, your pick beats the favorite, and "-" leaves a game to the source', () => {
    const picks = { '2026_11_BUF_KC': { team: 'KC', at }, '2026_11_NYJ_MIA': { team: 'NYJ', at }, '2026_12_KC_DEN': { team: 'KC', at } }
    const s = { on: true, decisions: new Map([['2026_11_BUF_KC', 'BUF'], ['2026_12_KC_DEN', '-']]), fav: true, usePicks: true }
    const d = decide(file, s, picks, 'student')
    expect(d.get('2026_11_BUF_KC')).toEqual({ winner: 'away', from: 'link' })
    expect(d.get('2026_11_NYJ_MIA')).toEqual({ winner: 'away', from: 'pick' })
    expect(d.has('2026_12_KC_DEN')).toBe(false)
    // picks off, favorites on: MIA is the Student's favorite (p_home 0.4 means NYJ... the away side)
    const off = decide(file, { ...s, usePicks: false, decisions: new Map() }, picks, 'student')
    expect(winners(off)).toEqual(new Map([['2026_11_BUF_KC', 'home'], ['2026_11_NYJ_MIA', 'away'], ['2026_12_KC_DEN', 'home']]))
    // the market's favorite differs
    expect(decide(file, { ...s, usePicks: false, decisions: new Map() }, picks, 'market').get('2026_11_BUF_KC')?.winner).toBe('away')
    expect(picksInPlay(file, picks)).toBe(3)
  })

  it('clicking the decided team undoes it; a pick is overridden with "-"', () => {
    const s = { on: true, decisions: new Map<string, string>(), fav: false, usePicks: true }
    const game = file.games[0]
    const a = toggle(s, game, 'BUF', undefined)
    expect(a.decisions.get(game.game_id)).toBe('BUF')
    expect(toggle(a, game, 'BUF', { winner: 'away', from: 'link' }).decisions.has(game.game_id)).toBe(false)
    expect(toggle(s, game, 'KC', { winner: 'home', from: 'pick' }).decisions.get(game.game_id)).toBe('-')
    expect(toggle(a, game, 'KC', { winner: 'away', from: 'link' }).decisions.get(game.game_id)).toBe('KC')
  })

  it('groups by week in kickoff order and ranks movers', () => {
    expect(gamesByWeek(file).map(([w, gs]) => [w, gs.map((x) => x.game_id)])).toEqual([[11, ['2026_11_NYJ_MIA', '2026_11_BUF_KC']], [12, ['2026_12_KC_DEN']]])
    const o = (p: number) => ({ playoffs: p }) as never
    expect(movers({ KC: o(0.5), BUF: o(0.8), MIA: o(0.3) }, { KC: o(0.9), BUF: o(0.7), MIA: o(0.31) }, ['KC', 'BUF', 'MIA'])).toEqual([
      { team: 'KC', from: 0.5, to: 0.9 },
      { team: 'BUF', from: 0.8, to: 0.7 },
    ])
  })
})
