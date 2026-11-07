import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { TeamsFile, type TeamFeature } from '../../data/contract'
import { extremes, pctOf } from './overview'

const feat = (id: string, better: 'higher' | 'lower' | null = 'higher'): TeamFeature =>
  ({ id, label: id, short: id, description: '', unit: 'count', group: 'g', group_name: 'G', better, n: 32, mean: 0, lo: 0, q1: 0, med: 0, q3: 0, hi: 0 }) as TeamFeature

function file(ranks: Record<string, number | undefined>, features: TeamFeature[]): TeamsFile {
  const rank: Record<string, number> = {}
  for (const [k, v] of Object.entries(ranks)) if (v !== undefined) rank[k] = v
  return { features, teams: { KC: { rank, values: {} } } } as unknown as TeamsFile
}

const ids = (xs: { feature: TeamFeature }[]) => xs.map((x) => x.feature.id)

describe('extremes', () => {
  const fs = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'].map((id) => feat(id))

  it('takes the three best and three worst, best first and worst last', () => {
    const e = extremes(file({ a: 5, b: 1, c: 30, d: 12, e: 2, f: 32, g: 20, h: 3 }, fs), 'KC')
    expect(ids(e.best)).toEqual(['b', 'e', 'h'])
    expect(ids(e.worst)).toEqual(['f', 'c', 'g'])
    expect(e.best[0].place).toBe(1)
    expect(e.worst[0].place).toBe(0)
  })

  it('breaks ties by registry order and never lists a measure twice', () => {
    const e = extremes(file({ a: 4, b: 4, c: 4, d: 4, e: 4, f: 4, g: 4, h: 4 }, fs), 'KC')
    expect(ids(e.best)).toEqual(['a', 'b', 'c'])
    expect(new Set([...ids(e.best), ...ids(e.worst)]).size).toBe(6)
  })

  it('skips missing ranks, style measures and unknown teams', () => {
    const features = [feat('a'), feat('style', null), feat('c'), feat('d')]
    const e = extremes(file({ a: 3, style: 1, c: undefined, d: 9 }, features), 'KC')
    expect(ids(e.best)).toEqual(['a'])
    expect(ids(e.worst)).toEqual(['d'])
    expect(extremes(file({ a: 1 }, features), 'ZZZ')).toEqual({ best: [], worst: [] })
  })

  it('splits fewer than six ranked measures without overlap', () => {
    const five = extremes(file({ a: 1, b: 2, c: 3, d: 4, e: 5 }, fs), 'KC')
    expect(ids(five.best)).toEqual(['a', 'b', 'c'])
    expect(ids(five.worst)).toEqual(['e', 'd'])
    const four = extremes(file({ a: 1, b: 2, c: 3, d: 4 }, fs), 'KC')
    expect(ids(four.best)).toEqual(['a', 'b'])
    expect(ids(four.worst)).toEqual(['d', 'c'])
    const one = extremes(file({ a: 7 }, fs), 'KC')
    expect(ids(one.best)).toEqual(['a'])
    expect(one.worst).toEqual([])
    expect(extremes(file({}, fs), 'KC')).toEqual({ best: [], worst: [] })
  })
})

describe('pctOf', () => {
  it('keeps a value inside the track', () => {
    expect(pctOf(5, 10)).toBe(50)
    expect(pctOf(12, 10)).toBe(100)
    expect(pctOf(3, 0)).toBe(0)
  })
})

describe('extremes leaves out play-caller history', () => {
  it('never lists a scheme prior as the team\'s best or worst', () => {
    const file = JSON.parse(fs.readFileSync(path.resolve(import.meta.dirname, '../../test/fixtures/site/teams.json'), 'utf8'))
    const t = TeamsFile.parse(file)
    for (const code of Object.keys(t.teams)) {
      const ex = extremes(t, code)
      for (const r of [...ex.best, ...ex.worst]) expect(r.feature.id.startsWith('scheme.')).toBe(false)
    }
  })
})

