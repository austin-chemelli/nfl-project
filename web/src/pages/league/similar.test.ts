import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { LeagueFile, SimilarFile, type SimilarFlag, type SimilarNeighbour } from '../../data/contract'
import { teamInfo } from '../../lib/teams'
import {
  closestText, defaultSimilarTeam, finishGrid, finishLevel, flagCard, flagGroups, laneOffsets, levelCounts, outcomeText, overlapSummary, poolYears,
  quantile, recordFrom, resolveSimilarTeam, rowSpread, seasonLabel, shareVerdict, similarRows,
} from './similar'

const FIX = path.resolve(import.meta.dirname, '../../test/fixtures/site')
const league = LeagueFile.parse(JSON.parse(fs.readFileSync(path.join(FIX, 'league.json'), 'utf8')))
const sim = SimilarFile.parse(JSON.parse(fs.readFileSync(path.join(FIX, 'similar.json'), 'utf8')))

const nb = (over: Partial<SimilarNeighbour>): SimilarNeighbour => ({ season: 2018, team: 'KC', dist: 1, rec_then: '6-2', final: '12-4-0', playoffs: true, round: 'conf', profile: [], closest: [], furthest: [], ...over })
const flag = (over: Partial<SimilarFlag>): SimilarFlag => ({ kind: 'red', measure: 'strength.epa_off_adj', label: 'Offense', rank: 27, quarter: 'bottom', outcome: 'made', peers: '5-2', widened: false, flagged: [11, 28], others: [58, 80], ...over })

describe('records and rounds', () => {
  it('prints records with an en dash and drops a zero tie count', () => {
    expect(recordFrom('7-9-0')).toBe('7–9')
    expect(recordFrom('8-7-1')).toBe('8–7–1')
    expect(recordFrom('6-2')).toBe('6–2')
  })
  it('says the round reached in words', () => {
    const o = (playoffs: boolean, round: string | null) => outcomeText({ playoffs, round })
    expect(o(false, null)).toBe('Missed the playoffs')
    expect(o(true, 'wc')).toBe('Lost in the wild-card round')
    expect(o(true, 'conf')).toBe('Lost the conference game')
    expect(o(true, 'champ')).toBe('Won the Super Bowl')
    expect(o(true, null)).toBe('Made the playoffs')
    expect(o(true, 'something-new')).toBe('Made the playoffs')
  })
  it('names old franchise codes as the franchise', () => {
    expect(teamInfo('SD').name).toBe('Los Angeles Chargers')
    expect(teamInfo('OAK').name).toBe('Las Vegas Raiders')
    expect(teamInfo('STL').name).toBe('Los Angeles Rams')
  })
})

describe('finish grid', () => {
  it('orders from the furthest round down, the nearer season first within a round', () => {
    const near = [nb({ season: 2001, playoffs: false, round: null }), nb({ season: 2002, round: 'wc' }), nb({ season: 2003, round: 'champ' }), nb({ season: 2004, round: 'wc' }), nb({ season: 2005, round: 'sb' }), nb({ season: 2006, playoffs: true, round: null })]
    expect(finishGrid(near).map((c) => c.n.season)).toEqual([2003, 2005, 2002, 2004, 2006, 2001])
    expect(finishGrid(near).map((c) => c.level)).toEqual([5, 4, 1, 1, 1, 0])
  })
  it('scores levels and counts them for the legend, zeros kept', () => {
    expect(finishLevel({ playoffs: true, round: 'div' })).toBe(2)
    const counts = levelCounts(finishGrid([nb({ round: 'conf' }), nb({ round: 'conf' }), nb({ playoffs: false, round: null })]))
    expect(counts.map((c) => c.count)).toEqual([0, 0, 2, 0, 0, 1])
    expect(counts[0].label).toBe('Won the Super Bowl')
  })
  it('names a season as in the tooltip', () => {
    expect(seasonLabel(nb({}))).toBe('2018 KC, 12–4, lost the conference game')
    expect(seasonLabel(nb({ playoffs: false, round: null, final: '7-9-0' }))).toBe('2018 KC, 7–9, missed the playoffs')
  })
  it('puts every fixture neighbour in the grid, the 25 of them', () => {
    expect(finishGrid(sim.teams.CHI.nearest)).toHaveLength(25)
  })
})

describe('flag sentences', () => {
  it('builds the offense card from the counts, on the same record', () => {
    const c = flagCard(flag({}))
    expect(c.title).toBe('Offense: 27th.')
    expect(c.body).toBe('Among past teams at 5-2, those with a bottom-quarter offense made the playoffs 11 of 28 times, against 58 of 80 for the rest.')
  })
  it('says give or take a win when widened, and a conference game for outcome conf', () => {
    const c = flagCard(flag({ kind: 'strength', measure: 'strength.elo_pre', label: 'Long-run rating', rank: 3, quarter: 'top', outcome: 'conf', widened: true, flagged: [16, 40], others: [20, 110] }))
    expect(c.title).toBe('Long-run rating: 3rd.')
    expect(c.body).toBe('Among past teams at 5-2, give or take a win, those with a top-quarter long-run rating reached a conference game 16 of 40 times, against 20 of 110 for the rest.')
  })
  it('has a template per kept measure', () => {
    const t = (measure: string, quarter: 'bottom' | 'top' = 'bottom') => flagCard(flag({ measure, quarter })).body
    expect(t('strength.qb_epa')).toContain('those with bottom-quarter QB play made')
    expect(t('strength.pythag_win_pct')).toContain('a bottom-quarter expected win rate')
    expect(t('strength.point_diff_pg', 'top')).toContain('a top-quarter point margin per game')
    expect(t('strength.epa_def')).toContain('a bottom-quarter defense')
    expect(t('form.last3_win_pct')).toContain('a bottom-quarter record over their last three games')
    expect(t('form.streak')).toContain('a bottom-quarter streak')
    expect(t('decisions.turnover_margin_pg')).toContain('a bottom-quarter turnover margin')
  })
  it('writes luck as the record undersells them', () => {
    const c = flagCard(flag({ kind: 'fine', measure: 'strength.luck', label: 'Luck', quarter: 'bottom' }))
    expect(c.title).toBe('Record undersells them.')
    expect(c.lead).toBe('Their scoring margin is better than their record.')
    expect(c.body).toContain('a scoring margin better than their record made the playoffs')
  })
  it('explains that a weak defense is on the same record', () => {
    expect(flagCard(flag({ kind: 'fine', measure: 'strength.epa_def', label: 'Defense' })).note).toMatch(/offense earned it/)
    expect(flagCard(flag({})).note).toBeNull()
  })
  it('falls back to a generic sentence for a measure it does not know', () => {
    expect(flagCard(flag({ measure: 'x.new_thing', label: 'New Thing' })).body).toContain('a bottom-quarter new Thing')
  })
  it('describes the share from the counts alone, with no percentages and no "will"', () => {
    expect(shareVerdict(flag({ flagged: [11, 28], others: [58, 80] }))).toBe('A smaller share than the rest')
    expect(shareVerdict(flag({ flagged: [30, 40], others: [40, 80] }))).toBe('A larger share than the rest')
    expect(shareVerdict(flag({ flagged: [20, 40], others: [41, 80] }))).toBe('About the same share as the rest')
    for (const f of sim.teams.CHI.flags) {
      const c = flagCard(f)
      const text = `${c.title} ${c.lead ?? ''} ${c.body} ${c.verdict} ${c.note ?? ''}`
      expect(text).not.toMatch(/%|\bwill\b/i)
      expect(text).toMatch(/Among past teams at/)
    }
  })
  it('groups red, looks-bad, strength in that order and drops empty groups', () => {
    const flags = [flag({ kind: 'strength', measure: 'strength.qb_epa' }), flag({ kind: 'red' }), flag({ kind: 'strength', measure: 'strength.elo_pre' })]
    const g = flagGroups(flags)
    expect(g.map((x) => x.title)).toEqual(['Red flags', 'Real strengths'])
    expect(g[1].cards).toHaveLength(2)
    expect(flagGroups([])).toEqual([])
    expect(flagGroups([flag({ kind: 'fine' })]).map((x) => x.title)).toEqual(["Looks bad, wasn't"])
  })
})

describe('the list', () => {
  it('lists the ten nearest and prints closest and furthest with the measure labels', () => {
    const rows = similarRows(sim.teams.CHI, sim.measures)
    expect(rows).toHaveLength(10)
    expect(rows[0].close).toMatch(/^Closest on .+ · furthest on .+$/)
    expect(closestText({ closest: ['record', 'strength.qb_epa'], furthest: ['strength.epa_def'] }, sim.measures)).toBe('Closest on Record, QB play · furthest on Defense')
    expect(closestText({ closest: [], furthest: ['strength.epa_def'] }, sim.measures)).toBe('Furthest on Defense')
    expect(closestText({ closest: [], furthest: [] }, sim.measures)).toBeNull()
  })
  it('picks the best playoff chance among teams with an entry, and never a team without one', () => {
    const best = Object.keys(sim.teams).sort((a, b) => league.odds.student.teams[b].playoffs - league.odds.student.teams[a].playoffs)[0]
    expect(defaultSimilarTeam(league, sim)).toBe(best)
    expect(defaultSimilarTeam(league, { ...sim, teams: {} })).toBeNull()
  })
  it('resolves ?team= to a team in the file, else the default', () => {
    expect(resolveSimilarTeam(league, sim, 'MIA')).toBe('MIA')
    expect(resolveSimilarTeam(league, sim, 'NO')).toBe('NO')
    expect(resolveSimilarTeam(league, sim, 'constructor')).toBe(defaultSimilarTeam(league, sim))
    expect(resolveSimilarTeam(league, null, null)).toBe(league.teams[0].team)
  })
})

describe('overlap chart arithmetic', () => {
  it('lays out the same dots the same way, never random, and keeps close dots apart', () => {
    const xs = [10, 12, 11, 50, 52, 90, 10.5]
    expect(laneOffsets(xs, 8)).toEqual(laneOffsets(xs, 8))
    const lanes = laneOffsets(xs, 8)
    for (let i = 0; i < xs.length; i++) for (let j = i + 1; j < xs.length; j++) if (Math.abs(xs[i] - xs[j]) < 8) expect(lanes[i]).not.toBe(lanes[j])
    expect(laneOffsets([5, 60], 8)).toEqual([0, 0])
  })
  it('takes lanes 0, +1, -1 in turn', () => {
    expect(laneOffsets([10, 10, 10, 10], 8)).toEqual([0, 1, -1, 2])
  })
  it('measures the middle half and how tight it is', () => {
    expect(quantile([1, 2, 3, 4, 5], 0.5)).toBe(3)
    const tight = rowSpread([50, 52, 54, 56, 58, 60, 62, 64])!
    expect(tight.tight).toBe('tight')
    const loose = rowSpread([5, 20, 40, 60, 80, 95, 10, 90])!
    expect(loose.tight).toBe('loose')
    expect(rowSpread([1, 2])).toBeNull()
  })
  it('summarizes for a screen reader', () => {
    const s = overlapSummary(sim.teams.CHI, sim.measures, 'Chicago Bears')
    expect(s).toContain('Record 71')
    expect(s).toContain('Schedule 62')
    expect(s).not.toMatch(/\bwill\b/i)
  })
})

describe('fine print years', () => {
  it('reads the pool', () => {
    expect(poolYears({ seasons: [2002, 2025], n: 768 })).toBe('2002 to 2025')
    expect(poolYears({ seasons: [2021, 2025], n: 160 })).toBe('2021 to 2025')
    expect(poolYears(undefined)).toBeNull()
  })
})
