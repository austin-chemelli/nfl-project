import { cleanup, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import { renderRoute } from '../../test/render'
import fixture from '../../test/fixtures/site/teams.json'

afterEach(cleanup)

const open = async (url: string) => {
  const { container } = renderRoute(url)
  await screen.findByRole('group', { name: 'Starting views' })
  return container
}

describe('Teams tab: compare', () => {
  it('?team=KC&vs=BUF opens the comparison with every published measure, in groups', async () => {
    await open('/league?tab=teams&team=KC&vs=BUF')
    const section = await screen.findByRole('region', { name: 'Kansas City Chiefs compared with Buffalo Bills' })
    expect(section).toHaveAttribute('data-matchup')
    expect(section.style.getPropertyValue('--team-away-light')).toMatch(/^#/)
    expect(section.style.getPropertyValue('--team-home-dark')).toMatch(/^#/)
    const details = Array.from(section.querySelectorAll('details'))
    expect(details.map((d) => d.querySelector('summary .font-medium')!.textContent)).toEqual(['Quality', 'Offense', 'Defense', 'Form', 'Coaching', 'Defensive scheme'])
    expect(details.filter((d) => d.open)).toHaveLength(1)
    expect(details[0].open).toBe(true)
    expect(section.querySelectorAll('li')).toHaveLength(fixture.features.length)
    // a measure where lower is better says so, and the values are written out for a reader without the chart
    expect(within(section).getAllByText('lower is better').length).toBeGreaterThan(0)
    expect(section).toHaveTextContent(/KC [^ ]+ \(\d+(st|nd|rd|th) of 32\)/)
  })

  it('picks a second team from the panel and clears it', async () => {
    await open('/league?tab=teams&team=KC')
    expect(screen.queryByRole('region', { name: /compared with/ })).toBeNull()
    const select = screen.getByLabelText('Compare with')
    expect(within(select).queryByRole('option', { name: 'Kansas City Chiefs' })).toBeNull()
    await userEvent.selectOptions(select, 'BUF')
    expect(await screen.findByRole('region', { name: 'Kansas City Chiefs compared with Buffalo Bills' })).toBeInTheDocument()
    expect(screen.getByLabelText('Compare with')).toHaveValue('BUF')
    await userEvent.selectOptions(screen.getByLabelText('Compare with'), '')
    expect(screen.queryByRole('region', { name: /compared with/ })).toBeNull()
    expect(screen.getByLabelText('Compare with')).toHaveValue('')
  })

  it('stopping the comparison and closing the panel both leave the page without it', async () => {
    await open('/league?tab=teams&team=KC&vs=BUF')
    await userEvent.click(await screen.findByRole('button', { name: 'Stop comparing' }))
    expect(screen.queryByRole('region', { name: /compared with/ })).toBeNull()
    expect(screen.getByLabelText('Compare with')).toHaveValue('')
  })

  it('ignores an unknown, same-team or team-less ?vs=', async () => {
    for (const url of ['/league?tab=teams&team=KC&vs=constructor', '/league?tab=teams&team=KC&vs=NOPE', '/league?tab=teams&team=KC&vs=KC', '/league?tab=teams&vs=BUF']) {
      await open(url)
      expect(screen.queryByRole('region', { name: /compared with/ })).toBeNull()
      cleanup()
    }
  })

  it('colors by the matchup slots, not a raw color', async () => {
    const c = await open('/league?tab=teams&team=KC&vs=BUF')
    const section = await screen.findByRole('region', { name: /compared with/ })
    expect(section.querySelector('[style*="var(--team-away)"]')).not.toBeNull()
    expect(section.querySelector('[style*="var(--team-home)"]')).not.toBeNull()
    expect(c.querySelector('section[data-matchup] circle[fill="var(--team-away)"]')).not.toBeNull()
  })

  it('moves focus to the comparison when it opens and back to the compare select when stopped', async () => {
    await open('/league?tab=teams&team=KC')
    await userEvent.selectOptions(screen.getByLabelText('Compare with'), 'BUF')
    const section = await screen.findByRole('region', { name: /compared with/ })
    expect(section).toHaveFocus()
    await userEvent.click(screen.getByRole('button', { name: 'Stop comparing' }))
    expect(screen.getByLabelText('Compare with')).toHaveFocus()
  })

  it('forgets the comparison team when it is picked as the team', async () => {
    await open('/league?tab=teams&team=KC&vs=BUF')
    await screen.findByRole('region', { name: /compared with/ })
    await userEvent.selectOptions(screen.getByLabelText('Find a team'), 'BUF')
    expect(screen.queryByRole('region', { name: /compared with/ })).toBeNull()
    await userEvent.selectOptions(screen.getByLabelText('Find a team'), 'KC')
    expect(screen.queryByRole('region', { name: /compared with/ })).toBeNull()
  })

  it('hides the row charts from assistive tech, since the values are printed, and says the line spans the whole league', async () => {
    await open('/league?tab=teams&team=KC&vs=BUF')
    const section = await screen.findByRole('region', { name: /compared with/ })
    expect(within(section).queryAllByRole('img')).toHaveLength(0)
    expect(section.querySelector('svg[aria-hidden="true"]')).not.toBeNull()
    expect(section).toHaveTextContent('lowest to the highest team in the league')
  })
})
