import { act, cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ScatterProps } from '../../charts/Scatter'
import { renderRoute } from '../../test/render'
import fixture from '../../test/fixtures/site/teams.json'

const last: { props: ScatterProps | null } = { props: null }
vi.mock('../../charts/Scatter', () => ({
  Scatter: (p: ScatterProps) => {
    last.props = p
    return <svg role="img" aria-label={p.label} />
  },
}))

afterEach(cleanup)

const open = async (url: string) => {
  renderRoute(url)
  await screen.findByRole('group', { name: 'Starting views' })
}
const pressed = () => screen.queryAllByRole('button', { pressed: true }).map((b) => b.textContent)

describe('Teams tab', () => {
  it('opens on preset 1', async () => {
    await open('/league')
    expect(screen.getByText(/^Every team on any two measures, entering its next game/)).toBeInTheDocument()
    expect(pressed()).toEqual(['Offense vs defense'])
    expect(last.props!.points).toHaveLength(32)
    expect(last.props!.y.flip).toBe(true)
    expect(last.props!.x.flip).toBe(false)
    expect(last.props!.quadrants![1]).toBe('Good on both sides')
  })

  it('falls back to preset 1 on an unknown ?x=', async () => {
    await open('/league?x=nope&y=strength.luck')
    expect(pressed()).toEqual(['Offense vs defense'])
  })

  it('a preset sets the axes and a selector change un-highlights it', async () => {
    await open('/league')
    await userEvent.click(screen.getByRole('button', { name: 'Luck vs margin' }))
    expect(pressed()).toEqual(['Luck vs margin'])
    expect(last.props!.x.title).toBe('Point margin')
    await userEvent.selectOptions(screen.getByLabelText('X axis'), 'strength.sos')
    expect(pressed().filter((t) => t !== 'Conference')).toEqual([])
    expect(last.props!.quadrants![0]).toBe('Lower schedule strength, higher luck')
  })

  it('swaps the axes with the button, templating the captions, and keeps ?tab=', async () => {
    await open('/league?tab=teams')
    await userEvent.click(screen.getByRole('button', { name: 'Swap axes' }))
    expect(last.props!.x.title).toBe('Defense EPA')
    expect(last.props!.x.flip).toBe(true)
    expect(screen.getByRole('tab', { name: 'Teams' })).toHaveAttribute('aria-selected', 'true')
  })

  it('groups the selector options by feature group', async () => {
    await open('/league')
    const groups = within(screen.getByLabelText('Y axis')).getAllByRole('group').map((g) => g.getAttribute('label'))
    expect(groups.slice(0, 3)).toEqual(['Quality', 'Offense', 'Defense'])
  })

  it('opens the panel on ?team=KC with game links, the next game, and a close control', async () => {
    await open('/league?team=KC')
    const panel = screen.getByRole('region', { name: /Kansas City Chiefs/ })
    const link = within(panel).getByRole('link', { name: /Wk 1 vs DEN.*W 31–10/ })
    expect(link).toHaveAttribute('href', '/game/2026_01_DEN_KC')
    expect(within(panel).getAllByRole('link').filter((a) => a.getAttribute('href')?.startsWith('/game/'))).toHaveLength(17)
    expect(within(panel).getByRole('link', { name: /Wk 9 vs NYJ.*next/ })).toBeInTheDocument()
    expect(within(panel).getByRole('link', { name: 'Scheme profile' })).toHaveAttribute('href', '/coaches?team=KC')
    expect(last.props!.selected).toBe('KC')
    await userEvent.click(within(panel).getByRole('button', { name: 'Close team panel' }))
    expect(screen.queryByRole('region', { name: /Kansas City Chiefs/ })).toBeNull()
  })

  it('selecting from the chart opens the panel', async () => {
    await open('/league')
    act(() => last.props!.onSelect!('GB'))
    expect(await screen.findByRole('region', { name: /Green Bay Packers/ })).toBeInTheDocument()
  })

  it('builds the hover card', async () => {
    await open('/league')
    const tip = within(renderTip().container)
    expect(tip.getByText('Kansas City Chiefs')).toBeInTheDocument()
    expect(tip.getByText('AFC West · 5–2')).toBeInTheDocument()
    expect(tip.getByText(/Offense EPA · 5th of 32/)).toBeInTheDocument()
    expect(tip.getByText('Through Week 8 · tap for games')).toBeInTheDocument()
  })

  it('shows the numbers: 32 rows', async () => {
    await open('/league')
    const table = screen.getByRole('table', { hidden: true })
    expect(within(table).getAllByRole('row', { hidden: true })).toHaveLength(33)
  })

  it('division mode shows eight chips; picking one strongs four teams and mutes the rest', async () => {
    await open('/league?color=division')
    const g = screen.getByRole('group', { name: 'Division' })
    expect(within(g).getAllByRole('button')).toHaveLength(8)
    await userEvent.click(within(g).getByRole('button', { name: 'NFC North' }))
    const tones = last.props!.points.map((p) => p.tone)
    expect(tones.filter((t) => t === 'strong')).toHaveLength(4)
    expect(tones.filter((t) => t === 'muted')).toHaveLength(28)
  })

  it('color None drops the tones', async () => {
    await open('/league?color=none')
    expect(last.props!.points.every((p) => p.tone === undefined)).toBe(true)
  })

  it('has one fine print', async () => {
    await open('/league')
    expect(screen.getAllByText('Fine print')).toHaveLength(1)
  })

  it('ignores a ?team= that is a property of every object', async () => {
    await open('/league?team=constructor')
    expect(screen.queryByRole('region', { name: /games$/ })).toBeNull()
    expect(last.props!.selected).toBeNull()
  })

  it('finds a team by name, opens its panel and moves focus there, and returns focus on close', async () => {
    await open('/league')
    await userEvent.selectOptions(screen.getByLabelText('Find a team'), 'KC')
    const panel = await screen.findByRole('region', { name: 'Kansas City Chiefs games' })
    expect(panel).toHaveFocus()
    expect(last.props!.selected).toBe('KC')
    await userEvent.click(within(panel).getByRole('button', { name: 'Close team panel' }))
    expect(screen.getByLabelText('Find a team')).toHaveFocus()
  })

  it('leaves focus alone on a shared link', async () => {
    await open('/league?team=KC')
    expect(screen.getByRole('region', { name: 'Kansas City Chiefs games' })).not.toHaveFocus()
  })

  it('says how far each team has played, not the league week', async () => {
    await open('/league?team=PIT')
    const panel = screen.getByRole('region', { name: 'Pittsburgh Steelers games' })
    const through = fixture.teams.PIT.through_week
    expect(within(panel).getByText(new RegExp(`through Week ${through}`))).toBeInTheDocument()
  })

  it('keeps the other axis out of each list, so a measure cannot sit on both', async () => {
    await open('/league')
    const options = within(screen.getByLabelText('X axis')).getAllByRole('option').map((o) => (o as HTMLOptionElement).value)
    expect(options).not.toContain('strength.epa_def')
    expect(options).toContain('strength.epa_off')
  })

  it('keeps the conference legend while no division is picked', async () => {
    await open('/league?color=division')
    expect(screen.getByText('AFC')).toBeInTheDocument()
    cleanup()
    await open('/league?color=division&div=AFC%20North')
    expect(screen.queryByText('AFC')).toBeNull()
  })

  it('explains the measure on each axis', async () => {
    await open('/league')
    expect(screen.getAllByRole('button', { name: /what|help|\?/i }).length).toBeGreaterThanOrEqual(2)
  })
})

function renderTip() {
  return render(<div>{last.props!.tip!('KC')}</div>)
}
