import { fireEvent, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderRoute } from '../../test/render'
import { resultText } from './format'

// the games table is the last table on the page (the week table sits behind a disclosure)
const gamesRows = () => {
  const tables = screen.getAllByRole('table')
  return within(tables[tables.length - 1]).getAllByRole('row').slice(1)
}

describe('Season page', () => {
  it('lists the 2025 games against the market', async () => {
    renderRoute('/season/2025')
    expect(await screen.findByRole('heading', { name: 'Every game' })).toBeInTheDocument()
    expect(screen.getByText('DAL @ PHI')).toBeInTheDocument()
    expect(screen.getByText('PHI by 4')).toBeInTheDocument()
    expect(screen.getAllByText('Picks right').length).toBeGreaterThan(0)
    expect(screen.getByText(/than the market\)|same as the market\)/)).toBeInTheDocument()
    // the Student is the default without ?w=
    expect(screen.getByRole('heading', { name: /The Student, 2025/ })).toBeInTheDocument()
    // 284 games + header row
    expect(gamesRows().length).toBe(284)
  })

  it('uses ?w= and filters by team', async () => {
    renderRoute('/season/2025?set=yours&w=quality:70,form:30&team=PHI')
    expect(await screen.findByRole('heading', { name: /Your weights, 2025/ })).toBeInTheDocument()
    const rows = gamesRows()
    expect(rows.length).toBeGreaterThan(10)
    expect(rows.length).toBeLessThan(25)
    for (const r of rows) expect(within(r).getAllByText(/PHI/).length).toBeGreaterThan(0)
    expect(screen.getByRole('link', { name: 'Back to Build your own' }).getAttribute('href')).toContain('quality:70,form:30')
  })

  it('sorts by a column', async () => {
    renderRoute('/season/2025?set=analyst')
    const btn = await screen.findByRole('button', { name: /Your home win/ })
    fireEvent.click(btn)
    const pcts = gamesRows().map((r) => parseFloat(within(r).getAllByRole('cell')[2].textContent ?? ''))
    expect(pcts).toEqual([...pcts].sort((a, b) => a - b))
  })

  it('says so for a season outside the data', async () => {
    renderRoute('/season/1999')
    expect(await screen.findByText('No games for 1999.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open 2025/ })).toBeInTheDocument()
  })
})

describe('resultText', () => {
  it('names the winner and margin', () => {
    expect(resultText({ result: -7, home: 'NO', away: 'ARI' })).toBe('ARI by 7')
    expect(resultText({ result: 0, home: 'NO', away: 'ARI' })).toBe('Tie')
    expect(resultText({ result: null, home: 'NO', away: 'ARI' })).toBe('–')
  })
})
