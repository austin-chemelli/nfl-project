import { describe, expect, it } from 'vitest'
import { screen, within } from '@testing-library/react'
import { renderRoute } from '../../test/render'

// CAR @ GB in the fixture: a lean toward CAR (the away team), three parts; tracker.json has a record.
describe('LeanBlock', () => {
  it('shows the lean toward its team, the range, the parts and the live record, all from the JSON', async () => {
    renderRoute('/game/2026_08_CAR_GB?tab=approaches')
    const block = await screen.findByTestId('lean')
    expect(within(block).getByText(/^History leans/).textContent).toMatch(/^History leans CAR by 0\.46 points against the market's spread/)
    expect(within(block).getByRole('img', { name: /^lean 0\.46 points toward CAR/ })).toBeInTheDocument()
    expect(within(block).getAllByTestId(/^lean-part-/)).toHaveLength(3)
    expect(await within(block).findByTestId('lean-record')).toHaveTextContent('Tracked since 2026 Week 10: 2 right, 1 wrong against the spread · a typical lean is 0.91 points.')
    expect(within(block).queryByTestId('lean-grade')).toBeNull() // not played in the fixture
    expect(block.textContent).not.toMatch(/chance|probab/i)
  })
})
