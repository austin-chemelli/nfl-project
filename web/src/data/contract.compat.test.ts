import fs from 'node:fs'
import path from 'node:path'
import { expect, it } from 'vitest'
import { Game, Meta, PathsOutcome } from './contract'

// The bucket can hold a meta.json published by an older image (before tendency labels existed);
// the site must still load.
it('accepts meta.json without the tendency labels', () => {
  const meta = JSON.parse(fs.readFileSync(path.resolve(import.meta.dirname, '../test/fixtures/site/meta.json'), 'utf8'))
  delete meta.tendency_metrics
  delete meta.tendency_situations
  const parsed = Meta.parse(meta)
  expect(parsed.tendency_metrics).toEqual({})
})

// Matchups and paths (ADR 0028, M25.3): game files published before they existed, and games with
// nothing to show, must still parse; the new sections default to null.
it('accepts a game without matchups, paths or paths_outcome, and meta without split_defs', () => {
  const fx = path.resolve(import.meta.dirname, '../test/fixtures/site')
  const game = JSON.parse(fs.readFileSync(path.join(fx, 'game/2026_08_CAR_GB.json'), 'utf8'))
  expect(Game.parse(game).matchups?.sides.length).toBe(2)
  for (const k of ['matchups', 'paths', 'paths_outcome']) delete game[k]
  const old = Game.parse(game)
  expect(old.matchups).toBeNull()
  expect(old.paths).toBeNull()
  expect(old.paths_outcome).toBeNull()
  const meta = JSON.parse(fs.readFileSync(path.join(fx, 'meta.json'), 'utf8'))
  expect(Object.keys(Meta.parse(meta).split_defs)).toContain('blitz')
  delete meta.split_defs
  expect(Meta.parse(meta).split_defs).toEqual({})
})

it('parses a paths_outcome', () => {
  const o = PathsOutcome.parse({
    game_id: '2026_08_CAR_GB', dog: 'CAR', favorite: 'GB', size: 7.5, bucket: '7-9.5', dog_won: false,
    tied: false, margin: -3, met: ['turnovers'], sentence: 'CAR won the turnover battle; it lost.',
    conditions: [{ id: 'turnovers', label: 'Win the turnover battle', met: true }],
  })
  expect(o.dog_won).toBe(false)
})
