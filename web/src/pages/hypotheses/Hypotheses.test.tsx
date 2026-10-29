import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { renderRoute } from '../../test/render'
import fixture from '../../test/fixtures/site/hypotheses.json'

describe('Hypotheses page', () => {
  it('renders each feature sentence and the verdict', async () => {
    renderRoute('/hypotheses')
    const first = fixture.features[0]
    expect(await screen.findByText(first.sentence)).toBeInTheDocument()
    expect(screen.getAllByText(/matters/i).length).toBeGreaterThan(0)
    expect(screen.queryByText(/logit|log-odds/i)).toBeNull()
  })

  it('switches the over-time item via ?item=', async () => {
    const key = 'availability.qb1_out'
    const it = fixture.by_season.items[key as keyof typeof fixture.by_season.items]
    renderRoute(`/hypotheses?item=${key}`)
    expect(await screen.findByText(it.sentence)).toBeInTheDocument()
    const select = screen.getByLabelText('Feature or group') as HTMLSelectElement
    expect(select.value).toBe(key)
  })

  it('changes the item from the picker', async () => {
    renderRoute('/hypotheses?item=availability.qb1_out')
    const select = (await screen.findByLabelText('Feature or group')) as HTMLSelectElement
    const other = fixture.by_season.items['availability.injury_impact' as keyof typeof fixture.by_season.items]
    await userEvent.selectOptions(select, 'availability.injury_impact')
    await waitFor(() => expect(screen.getByText(other.sentence)).toBeInTheDocument())
    expect(within(select).getAllByRole('option').length).toBeGreaterThan(1)
  })
})
