import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Game } from '../data/contract'
import { FaceOff } from './FaceOff'
import { ordinal } from '../lib/rank'

const FIX = path.resolve(import.meta.dirname, '../test/fixtures/site/game/2026_08_CAR_GB.json')
const g = Game.parse(JSON.parse(fs.readFileSync(FIX, 'utf8')))
const colorOf = (t: string) => (t === g.home ? 'var(--team-home)' : 'var(--team-away)')

describe('FaceOff', () => {
  it('ordinal', () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 32].map(ordinal)).toEqual(['1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '22nd', '32nd'])
  })

  for (const i of [0, 1]) {
    it(`draws side ${i}'s ranks from the JSON with a pill for each edge`, () => {
      const side = g.matchups!.sides[i]
      expect(side.face_off.length).toBeGreaterThan(0)
      render(<FaceOff rows={side.face_off} offense={side.offense} defense={side.defense} colorOf={colorOf} />)
      for (const r of side.face_off) {
        const row = screen.getByTestId(`face-${r.id}`)
        expect(row).toHaveAttribute('data-edge', r.edge)
        expect(row.textContent).toContain(ordinal(r.off_rank))
        expect(row.textContent).toContain(ordinal(r.def_rank))
        const pill = row.querySelector('[data-testid="face-pill"]')
        if (r.edge === 'even') expect(pill).toBeNull()
        else expect(pill?.getAttribute('data-team')).toBe(r.edge === 'offense' ? side.offense : side.defense)
      }
    })
  }

  it('draws nothing without rows', () => {
    const { container } = render(<FaceOff rows={[]} offense="A" defense="B" colorOf={colorOf} />)
    expect(container).toBeEmptyDOMElement()
  })
})
