import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MatchupGrid, type SplitDef } from './MatchupGrid'
import { Game } from '../data/contract'

const dir = path.resolve(__dirname, '../test/fixtures/site/game')
const load = (id: string) => Game.parse(JSON.parse(fs.readFileSync(path.join(dir, `${id}.json`), 'utf8')))
const defs: Record<string, SplitDef> = { blitz: { label: 'Blitz', definition: 'A dropback with a blitzer.' } }

describe('MatchupGrid', () => {
  for (const id of ['2026_08_CAR_GB', '2026_08_ARI_DAL']) {
    it(`renders both sides of ${id} from the JSON`, () => {
      const g = load(id)
      const m = g.matchups!
      expect(m.sides.length).toBeGreaterThan(0)
      for (const side of m.sides) {
        const { unmount } = render(<MatchupGrid side={side} home={g.home} away={g.away} defs={defs} />)
        expect(screen.getByText(`Situations: ${side.offense} offense vs ${side.defense} defense`)).toBeInTheDocument()
        for (const r of side.rows) expect(screen.getByTestId(`row-${r.split}`)).toBeInTheDocument()
        // edge pills carry the edge from the file, in the colour of the team it favours
        const edged = side.rows.filter((r) => r.has_edge && r.favours && r.edge_pts_pg != null)
        const pills = screen.getAllByTestId('edge-pill')
        expect(pills).toHaveLength(edged.length)
        for (const r of edged) {
          const pill = within(screen.getByTestId(`row-${r.split}`)).getByTestId('edge-pill')
          const team = r.favours === 'offense' ? side.offense : side.defense
          expect(pill).toHaveAttribute('data-team', team)
          expect(pill.textContent).toBe(`+${Math.abs(r.edge_pts_pg!).toFixed(2)} ${team}`)
          expect(pill.style.borderColor).toBe(team === g.home ? 'var(--team-home)' : 'var(--team-away)')
        }
        unmount()
      }
    })
  }

  it('context rows have no edge pill and no habit band', () => {
    const g = load('2026_08_CAR_GB')
    const side = g.matchups!.sides[0]
    render(<MatchupGrid side={side} home={g.home} away={g.away} defs={defs} />)
    const ctx = side.rows.filter((r) => !r.has_edge)
    expect(ctx.length).toBeGreaterThan(0)
    for (const r of ctx) {
      const row = screen.getByTestId(`row-${r.split}`)
      expect(row).toHaveAttribute('data-edge', 'no')
      expect(within(row).queryByTestId('edge-pill')).toBeNull()
    }
    expect(screen.getByRole('group', { name: 'Context (no edge)' })).toBeInTheDocument()
  })

  it('places the habit dot and the faced tick inside the band, and labels reliability', () => {
    const g = load('2026_08_CAR_GB')
    const side = g.matchups!.sides[0]
    const r = side.rows.find((x) => x.has_edge && x.opp_rate != null)!
    render(<MatchupGrid side={side} home={g.home} away={g.away} defs={defs} />)
    const row = screen.getByTestId(`row-${r.split}`)
    expect(within(row).getByTestId('habit-dot')).toBeInTheDocument()
    expect(within(row).getByTestId('faced-tick')).toBeInTheDocument()
    expect(within(row).getByText(`(${r.reliability})`)).toBeInTheDocument()
  })
})
