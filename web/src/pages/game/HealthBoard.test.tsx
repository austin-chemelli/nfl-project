import fs from 'node:fs'
import path from 'node:path'
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Game, HealthBoard } from '../../data/contract'
import { HealthBoardView } from './HealthBoard'
import { InjuryReport } from './InjuryReport'

const room = (team: string, grp: string, name: string, rank: number, now = rank, missing: { player: string; status: string; out: boolean; key?: boolean }[] = []) =>
  ({ team, grp, name, rank, label: rank <= 14 ? 'good' : 'weak', now_rank: now, now_label: now <= 14 ? 'good' : 'weak', health: 1, missing })

const BOARD = HealthBoard.parse({
  lede: "BAL's receivers (#7, good) face CAR's corners, usually good (#12) but about #29 now with Mike Jackson and Jaycee Horn out.",
  notes: ["BAL's quarterback room goes from #7 to about #30 with Lamar Jackson out."],
  sides: [
    {
      offense: 'BAL', defense: 'CAR',
      rows: [
        { offense: room('BAL', 'WR', 'receivers', 7), defense: room('CAR', 'CB', 'corners', 12, 29, [{ player: 'Jaycee Horn', status: 'IR', out: true, key: true }, { player: 'Will Lee III', status: 'Questionable', out: false }]), favours: 'BAL', moved: true, flag: true, sentence: 'the WR line' },
        { offense: room('BAL', 'OL', 'offensive line', 17), defense: room('CAR', 'DL', 'interior line', 12), favours: null, moved: false, flag: false, sentence: null },
      ],
    },
    { offense: 'CAR', defense: 'BAL', rows: [] },
  ],
})
const colorOf = (t: string) => (t === 'CAR' ? 'var(--team-home)' : 'var(--team-away)')

describe('HealthBoardView', () => {
  it('pairs rooms that face each other, with both ranks, the pill and the flagged sentence', () => {
    render(<HealthBoardView board={BOARD} colorOf={colorOf} />)
    expect(screen.getByText(/The biggest change:/).parentElement).toHaveTextContent(/usually good \(#12\) but about #29 now/)
    const wr = screen.getByTestId('board-row-BAL-WR-CB')
    expect(wr).toHaveAttribute('data-flag', 'true')
    expect(wr).toHaveTextContent('#12 → ~#29') // usually good, weak now
    expect(wr).toHaveTextContent('#7')
    expect(wr).toHaveTextContent('out: Jaycee Horn') // a questionable player isn't "out"
    expect(wr).not.toHaveTextContent('Will Lee')
    expect(within(wr).getByTestId('board-verdict')).toHaveAttribute('data-team', 'BAL')
    expect(within(wr).getByText('injuries moved it')).toBeInTheDocument()
    expect(within(wr).getByText('the WR line')).toBeInTheDocument()
    const ol = screen.getByTestId('board-row-BAL-OL-DL')
    expect(ol).not.toHaveAttribute('data-flag')
    expect(within(ol).getByTestId('board-verdict').textContent).toBe('even')
    expect(screen.getByText(/quarterback room goes from #7 to about #30/)).toBeInTheDocument()
  })
})

describe('InjuryReport', () => {
  const FIX = path.resolve(import.meta.dirname, '../../test/fixtures/site/game/2026_08_CAR_GB.json')
  const base = Game.parse(JSON.parse(fs.readFileSync(FIX, 'utf8')))
  const inj = (player: string, pos: string, status: string, gsis_id: string, practice: string | null = null) => ({ week: 8, team: base.home, player, pos, status, practice, injury: 'Knee', gsis_id })

  it('groups by status with key players first, one line each, and the reserve-list starters last', () => {
    const starters = [
      { gsis_id: 'k1', slot: 'WR1', unit: 'offense', player: 'Key Receiver', grp: 'WR', value_pts: null, status: 'Questionable', p_play: 0.7, missing_pts: null, key: true },
      { gsis_id: 'r1', slot: 'LT', unit: 'offense', player: 'Tackle On IR', grp: 'OL', value_pts: null, status: 'IR', reserve: true, p_play: 0, missing_pts: null, key: true },
    ]
    const g = Game.parse({
      ...base,
      injuries: [inj('Role Player', 'LB', 'Questionable', 'x1', 'Full Participation in Practice'), inj('Key Receiver', 'WR', 'Questionable', 'k1'), inj('Out Guy', 'CB', 'Out', 'x2', 'Did Not Participate In Practice'), inj('Maybe Not', 'S', 'Doubtful', 'x3')],
      health: { home: { health: 0.9, missing_pts: 0, full_pts: 1, starters }, away: null },
    })
    render(<InjuryReport g={g} />)
    const home = screen.getByTestId(`report-${g.home}`)
    expect(within(home).queryByRole('table')).toBeNull() // lines, not a wide table
    const items = within(home).getAllByRole('listitem').map((li) => li.textContent!.replace(/\s+/g, ''))
    expect(items[0]).toBe('OutGuyCB·knee·nopractice')
    expect(items[1]).toBe('MaybeNotS·Doubtful·knee')
    expect(items[2]).toMatch(/^KeyReceiverWRkey/) // key first among the questionable
    expect(items[3]).toBe('RolePlayerLB·knee·fullpractice')
    expect(screen.getByTestId(`reserve-${g.home}`)).toHaveTextContent('Starters on reserve lists: Tackle On IR LT (key) · IR')
    expect(screen.getByTestId(`report-${g.away}`)).toHaveTextContent('None listed with a game status.')
  })
})
