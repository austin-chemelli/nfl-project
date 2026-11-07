import { describe, expect, it } from 'vitest'
import type { TeamFile } from '../../data/contract'
import car from '../../test/fixtures/site/team/CAR.json'
import { careerLine, changeLines, evidenceLabel, otherStaff } from './staff'

const row = (role: string, name: string, week: number, replaced: string | null = null) =>
  ({ role, name, start_week: week, end_week: null, evidence: 'official', confirmed: true, source_url: null, replaced })

describe('changeLines', () => {
  it('merges a title change and a play-calling change into one line', () => {
    expect(changeLines([row('DC', 'Todd Wash', 9, 'Ejiro Evero'), row('DEF_PC', 'Todd Wash', 9)])).toEqual([
      { week: 9, text: 'Week 9: Todd Wash took over the defense from Ejiro Evero' },
    ])
  })
  it('uses the play-caller row replaced when the title row has none', () => {
    expect(changeLines([row('OC', 'A B', 3), row('OFF_PC', 'A B', 3, 'C D')])[0].text).toBe('Week 3: A B took over the offense from C D')
  })
  it('handles a null replaced', () => {
    expect(changeLines([row('DC', 'Todd Wash', 9), row('DEF_PC', 'Todd Wash', 9)])[0].text).toBe('Week 9: Todd Wash took over the defense')
  })
  it('writes a play-calling-only change', () => {
    expect(changeLines([row('OFF_PC', 'Sean Payton', 5, 'Davis Webb')])[0].text).toBe('Week 5: Sean Payton took over the offensive play-calling from Davis Webb')
  })
  it('writes a head coach change and sorts by week', () => {
    const l = changeLines([row('HC', 'X Y', 11), row('OFF_PC', 'Sean Payton', 5)])
    expect(l.map((x) => x.text)).toEqual(['Week 5: Sean Payton took over the offensive play-calling', 'Week 11: X Y became head coach'])
  })
})

describe('careerLine', () => {
  it('prints ranges and single seasons', () => {
    expect(careerLine([{ team: 'MIA', from: 2022, to: 2025 }, { team: 'LAC', from: 2026, to: 2026 }])).toBe('MIA 2022–25, LAC 2026')
  })
})

describe('evidenceLabel', () => {
  it('maps kinds', () => {
    expect([evidenceLabel('official'), evidenceLabel('news'), evidenceLabel('roundup'), evidenceLabel('x')]).toEqual(['Team site', 'News', '32-team list', null])
  })
})

describe('otherStaff', () => {
  const file = car as unknown as TeamFile
  it('skips callers and names nobody twice', () => {
    const names = otherStaff(file).map((s) => s.name)
    expect(names).toEqual(['Dave Canales'])
  })
  it('keeps co-coordinators and drops a head coach shown as a caller', () => {
    const f = structuredClone(file)
    f.staff.current.push(row('OC', 'Second Oc', 1), row('OC', 'Second Oc', 1))
    f.units.off.caller = { ...f.units.off.caller!, name: 'Dave Canales', is_head_coach: true }
    expect(otherStaff(f).map((s) => s.name)).toEqual(['Brad Idzik', 'Second Oc'])
  })
})
