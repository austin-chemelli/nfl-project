import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { renderRoute } from '../../test/render'
import fixture from '../../test/fixtures/site/coaches.json'

describe('Coaches page', () => {
  it('shows the page header before data and a team callers with ?team=', async () => {
    renderRoute('/coaches?team=ARI')
    expect(await screen.findByRole('heading', { level: 1, name: /Coaches/ })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: /Nathaniel Hackett/ })).toBeInTheDocument()
    expect(screen.getByText(fixture.teams.ARI.off!.sentence)).toBeInTheDocument()
    expect(screen.getByText(/Head coach:/).parentElement).toHaveTextContent(fixture.teams.ARI.head_coach)
    expect(screen.getByText(/validated by hand/)).toBeInTheDocument()
  })

  it('handles a team with no defensive play-caller', async () => {
    renderRoute('/coaches?team=TB')
    expect(await screen.findByText(/No play-caller established/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Zac Robinson/ })).toBeInTheDocument()
  })

  it('switches teams from the picker', async () => {
    renderRoute('/coaches?team=ARI')
    const select = await screen.findByLabelText(/Team \(/)
    await userEvent.selectOptions(select, 'TB')
    await waitFor(() => expect(screen.getByRole('heading', { name: /Zac Robinson/ })).toBeInTheDocument())
    expect(within(select as HTMLElement).getAllByRole('option')).toHaveLength(32)
  })

  it('renders a coach view for a person via ?coach=', async () => {
    const p = fixture.people.find((x) => x.name === 'Adam Gase')!
    renderRoute('/coaches?coach=Adam%20Gase')
    expect(await screen.findByRole('heading', { name: /Adam Gase: offense/i })).toBeInTheDocument()
    expect(screen.getByText(p.sides[0].summary!.sentence)).toBeInTheDocument()
    expect(screen.getAllByText(/Primary QB/).length).toBeGreaterThan(0)
    const first = p.sides[0].seasons[0]
    expect(screen.getAllByText(new RegExp(`${first.season}`)).length).toBeGreaterThan(0)
  })

  it('says so when the coach is unknown', async () => {
    renderRoute('/coaches?coach=Nobody')
    expect(await screen.findByText(/No coach named "Nobody"/)).toBeInTheDocument()
  })
})
