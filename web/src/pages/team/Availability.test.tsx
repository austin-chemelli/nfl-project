import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'
import { TeamAvailability, type TeamFile } from '../../data/contract'
import { Availability } from './Availability'

afterEach(cleanup)

const kp = { player: 'Sam Star', pos: 'WR', grp: 'WR', status: 'Questionable', p_play: 0.6, p_play_n: 40, value_pts: 1.5, at_risk: 0.6, sentence: 'Sam Star is Questionable; worth 1.5 points.' }
const make = (over: Record<string, unknown> = {}) => ({
  availability: TeamAvailability.parse({
    week: 11,
    reported: true,
    value_at_risk: 0.6,
    players: [
      { player: 'Sam Star', grp: 'WR', value_pts: 1.5, status: 'Questionable', p_play: 0.6, at_risk: 0.6 },
      { player: 'Healthy Joe', grp: 'QB', value_pts: 3.2, status: null, p_play: null, at_risk: null },
    ],
    listed: [kp],
    ...over,
  }),
}) as unknown as TeamFile
const ui = (f: TeamFile) => render(<MemoryRouter><Availability file={f} /></MemoryRouter>)

describe('Availability panel', () => {
  it('shows values, statuses and the value at risk; an unlisted player has no status', () => {
    ui(make())
    expect(screen.getByText(/0\.6 points of value at risk this week/)).toBeInTheDocument()
    expect(screen.getByText('3.2')).toBeInTheDocument()
    expect(screen.getByText('Questionable')).toBeInTheDocument()
    expect(screen.getByText('60%')).toBeInTheDocument()
    const row = screen.getByText('Healthy Joe').closest('tr')!
    expect(row.textContent).not.toMatch(/Questionable|Doubtful|Out/)
    expect(screen.getByText('Sam Star is Questionable; worth 1.5 points.')).toBeInTheDocument()
  })

  it('says no report yet and shows no points at risk when not reported', () => {
    ui(make({ reported: false, value_at_risk: null, listed: [] }))
    expect(screen.getAllByText(/No injury report yet this week/).length).toBeGreaterThan(0)
    expect(screen.queryByText(/points of value at risk/)).toBeNull()
    expect(screen.queryByText(/ 0 points/)).toBeNull()
  })

  it('renders nothing when availability is null', () => {
    const { container } = ui({ availability: null } as unknown as TeamFile)
    expect(container).toBeEmptyDOMElement()
  })
})
