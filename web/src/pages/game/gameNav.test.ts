import { describe, expect, it } from 'vitest'
import slateJson from '../../test/fixtures/site/slate_2026_08.json'
import { Slate } from '../../data/contract'
import { arrowStepsGames, gameHref, slateNeighbours, weekOf } from './gameNav'

const games = Slate.parse(slateJson).games

describe('game nav', () => {
  it('reads the season and week from the id', () => {
    expect(weekOf('2026_08_CAR_GB')).toEqual({ season: 2026, week: 8 })
    expect(weekOf('nope')).toBeNull()
    expect(weekOf(undefined)).toBeNull()
  })

  it('steps in the slate order (kickoff, ties as listed), whatever order the file has', () => {
    const shuffled = [...games.slice(1), games[0]] // the Thursday game listed last
    const mid = slateNeighbours(shuffled, '2026_08_ARI_DAL')
    expect(mid.prev?.game_id).toBe('2026_08_CAR_GB')
    expect(mid.next?.game_id).toBe('2026_08_ATL_TB')
    expect([mid.index, mid.total]).toEqual([1, 14])
    // the Sunday-afternoon tie at 18:00Z keeps the file's order, like the slate page
    expect(slateNeighbours(games, '2026_08_BAL_BUF').prev?.game_id).toBe('2026_08_ATL_TB')
  })

  it('has no previous on the first game and no next on the last (no wrap-around)', () => {
    const first = slateNeighbours(games, '2026_08_CAR_GB')
    expect(first.prev).toBeNull()
    expect(first.next?.game_id).toBe('2026_08_ARI_DAL')
    const last = slateNeighbours(games, '2026_08_CHI_SEA')
    expect(last.next).toBeNull()
    expect(last.prev).toEqual({ game_id: '2026_08_PHI_WAS', away: 'PHI', home: 'WAS' })
    expect(slateNeighbours(games, '2026_08_XXX_YYY')).toMatchObject({ prev: null, next: null, index: -1 })
  })

  it('keeps the tab in the link', () => {
    expect(gameHref('2026_08_CAR_GB', 'retro')).toBe('/game/2026_08_CAR_GB?tab=retro')
    expect(gameHref('2026_08_CAR_GB', null)).toBe('/game/2026_08_CAR_GB')
  })

  it('arrow keys step games only outside inputs and widgets that own the arrows', () => {
    const key = (k: string, target: EventTarget | null, extra: Partial<KeyboardEvent> = {}) =>
      arrowStepsGames({ key: k, altKey: false, ctrlKey: false, metaKey: false, shiftKey: false, defaultPrevented: false, target, ...extra })
    const div = document.createElement('div')
    const input = document.createElement('input')
    const tab = document.createElement('button')
    tab.setAttribute('role', 'tab')
    expect(key('ArrowRight', document.body)).toBe(true)
    expect(key('ArrowLeft', div)).toBe(true)
    expect(key('ArrowDown', div)).toBe(false)
    expect(key('ArrowRight', input)).toBe(false)
    expect(key('ArrowRight', tab)).toBe(false)
    expect(key('ArrowRight', div, { metaKey: true })).toBe(false)
    expect(key('ArrowRight', div, { defaultPrevented: true })).toBe(false)
  })
})
