import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderRoute } from '../../test/render'
import { resetSavedCache, YOU_KEY } from '../../you/store'
import { gameLabel, headingShares } from './points'

describe('Build page', () => {
  it('renders presets, sliders by heading and a result line against the market', async () => {
    renderRoute('/build')
    expect(await screen.findByRole('button', { name: 'Blank (equal weights)' })).toBeInTheDocument()
    for (const name of ['The Traditionalist', 'The Analyst', 'The Sharp', 'What the data says (The Student)']) {
      expect(screen.getByRole('button', { name: name })).toBeInTheDocument()
    }
    expect(screen.getAllByText("Who's better").length).toBeGreaterThan(0)
    expect(screen.getByRole('slider', { name: /Quality/ })).not.toBeDisabled()
    // live-only groups can be weighted (they count in the live line) and say why history can't test them
    expect(screen.getByRole('slider', { name: /^Buzz/ })).not.toBeDisabled()
    expect(screen.getAllByText(/Live only: no history/).length).toBeGreaterThan(0)
    // context-only groups aren't sliders
    expect(screen.queryByRole('slider', { name: /^Coaching/ })).toBeNull()
    // headline against the market (never a bare log loss)
    expect((await screen.findAllByText(/\d\.\d{3} \((\d\.\d{3} (better|worse) than|same as) the market\)/)).length).toBeGreaterThan(1)
    expect(screen.getByText('The market (vig removed)')).toBeInTheDocument()
    expect(screen.getByText('Against The Student')).toBeInTheDocument()
  })

  it('moving a slider rewrites the budget and the URL share string', async () => {
    renderRoute('/build?w=quality:60,form:-40')
    const slider = await screen.findByRole('slider', { name: /Quality/ })
    expect(slider).toHaveValue('60')
    expect(screen.getByRole('slider', { name: /Form/ })).toHaveValue('40')
    expect(screen.getByText(/You spent 100 points/)).toBeInTheDocument()
    fireEvent.change(slider, { target: { value: '20' } })
    await waitFor(() => expect(screen.getByRole('slider', { name: /Quality/ })).toHaveValue('20'))
    expect(screen.getByText(/You spent 60 points/)).toBeInTheDocument()
  })

  it('a drag settles once: the share string follows the last value, not every step', async () => {
    renderRoute('/build?w=quality:60,form:-40')
    const slider = await screen.findByRole('slider', { name: /Quality/ })
    for (let v = 59; v >= 5; v--) fireEvent.change(slider, { target: { value: String(v) } })
    expect(slider).toHaveValue('5')
    await waitFor(() => {
      const hrefs = screen.getAllByRole('link').map((a) => a.getAttribute('href') ?? '')
      expect(hrefs.some((h) => h.includes('/season/') && /quality:5(,|$)/.test(h))).toBe(true)
    })
  })

  it('a preset sets the sliders, and the season link carries the weights', async () => {
    renderRoute('/build')
    fireEvent.click(await screen.findByRole('button', { name: 'The Sharp' }))
    await waitFor(() => expect(screen.getByRole('slider', { name: /Quarterback/ })).toHaveValue('100'))
    const link = await screen.findAllByRole('link', { name: /See every \d{4} game with your weights/ })
    expect(link[0].getAttribute('href')).toMatch(/^\/season\/\d{4}\?set=yours&w=.*quarterback:100/)
  })

  it('"Fit toward you" shows what history would change', async () => {
    renderRoute('/build?w=quality:50,offense:50')
    fireEvent.click(await screen.findByRole('button', { name: 'Fit toward you' }))
    expect(await screen.findByRole('button', { name: 'Use these weights' })).toBeInTheDocument()
  })

  it('saves the sliders as your approach, makes it the default, and starts from it next time', async () => {
    localStorage.clear()
    resetSavedCache()
    const { unmount } = renderRoute('/build?w=quality:60,form:-40')
    fireEvent.click(await screen.findByRole('button', { name: 'Save as my approach' }))
    const saved = JSON.parse(localStorage.getItem(YOU_KEY) ?? 'null')
    expect(saved).toMatchObject({ v: 1, name: 'You', points: { quality: 60, form: -40 }, registry: '7', is_default: false })
    expect(saved.calib.key).toMatch(/^7-2025-[0-9a-f]{8}$/)
    expect(Number.isFinite(saved.calib.a) && Number.isFinite(saved.calib.c)).toBe(true)
    fireEvent.click(screen.getByRole('checkbox', { name: /Make it my default/ }))
    expect(JSON.parse(localStorage.getItem(YOU_KEY) ?? 'null').is_default).toBe(true)
    unmount()
    renderRoute('/build')
    await waitFor(() => expect(screen.getByRole('slider', { name: /Quality/ })).toHaveValue('60'))
    expect(screen.getByRole('button', { name: /Your saved approach \(You\)/ })).toBeInTheDocument()
    localStorage.clear()
    resetSavedCache()
  })

  it('asks for points when the budget is empty', async () => {
    renderRoute('/build?w=')
    expect(await screen.findByText('Give at least one group some points.')).toBeInTheDocument()
    expect(within(document.body).queryByText('How you would have done')).toBeNull()
  })
})

describe('helpers', () => {
  it('labels games like the Streamlit page', () => {
    expect(gameLabel('2015_03_GB_CHI')).toBe('2015 W3: GB @ CHI')
    expect(gameLabel('weird')).toBe('weird')
  })
  it('sums the budget by heading in meta order', () => {
    const groups = [
      { id: 'a', heading: 'H1' }, { id: 'b', heading: 'H1' }, { id: 'c', heading: 'H2' },
    ] as never
    expect(headingShares({ a: 0.25, b: -0.25, c: 0.5 }, groups, ['H2', 'H1'])).toEqual([
      { heading: 'H2', share: 50 }, { heading: 'H1', share: 50 },
    ])
  })
})
