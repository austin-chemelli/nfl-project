import { cleanup, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import { renderRoute } from '../../test/render'

afterEach(cleanup)

const open = async () => {
  renderRoute('/league?tab=teams')
  await screen.findByRole('group', { name: 'Starting views' })
  const details = screen.getByText('Show the ranks').closest('details')!
  return { details, table: within(details).getByRole('table', { name: 'Every team on the starting-view measures' }) }
}
const names = (table: HTMLElement) => within(table).getAllByRole('rowheader').map((r) => r.textContent)

describe('Teams tab: rank table', () => {
  it('sits behind "Show the ranks", next to the existing numbers table, with 32 named rows', async () => {
    const { details, table } = await open()
    expect(details.open).toBe(false)
    expect(screen.getAllByText(/^Show the (numbers|ranks)$/).map((e) => e.textContent)).toEqual(['Show the numbers', 'Show the ranks'])
    expect(names(table)).toHaveLength(32)
    expect(names(table)[0]).toBe('Arizona Cardinals')
    expect(within(table).getByRole('columnheader', { name: /^Team/ })).toHaveAttribute('aria-sort', 'ascending')
  })

  it('sorts from a header button, reports aria-sort, and flips on a second press', async () => {
    const { table } = await open()
    const head = within(table).getByRole('columnheader', { name: /Defense EPA/ })
    expect(head).toHaveAttribute('aria-sort', 'none')
    await userEvent.click(within(head).getByRole('button'))
    expect(head).toHaveAttribute('aria-sort', 'ascending') // lower defense EPA is better, so best first is ascending
    expect(within(table).getByRole('columnheader', { name: /^Team/ })).toHaveAttribute('aria-sort', 'none')
    const first = names(table)
    await userEvent.click(within(head).getByRole('button'))
    expect(head).toHaveAttribute('aria-sort', 'descending')
    expect(names(table)[0]).toBe(first[first.length - 1])
  })

  it('is reachable and operable from the keyboard', async () => {
    const { table } = await open()
    const head = within(table).getByRole('columnheader', { name: /Offense EPA/ })
    within(head).getByRole('button').focus()
    await userEvent.keyboard('{Enter}')
    expect(head).toHaveAttribute('aria-sort', 'descending')
  })

  it('shades with a theme token at an opacity, best darkest, never a raw color', async () => {
    const { table } = await open()
    const cells = Array.from(table.querySelectorAll('td[data-shade]')) as HTMLElement[]
    expect(cells.length).toBeGreaterThan(100)
    for (const c of cells) {
      expect(c.className).toMatch(/color-mix\(in_srgb,var\(--(accent|band-strong)\)_var\(--shade\),transparent\)/)
      expect(c.style.getPropertyValue('--shade')).toMatch(/^\d+%$/)
    }
    const best = cells.filter((c) => c.dataset.shade === '45')
    expect(best.length).toBeGreaterThan(0)
    expect(table.innerHTML).not.toMatch(/#[0-9a-f]{6}/i)
  })

  it('scrolls inside the table box, not the page', async () => {
    const { table } = await open()
    expect(table.closest('.overflow-x-auto')).not.toBeNull()
  })

  it('does not call 1 the best where a measure has no good direction, and keeps ranks in full ink on shaded cells', async () => {
    const { table } = await open()
    const note = document.body.textContent ?? ''
    expect(note).toMatch(/where it has none \(such as Luck or Schedule strength\), 1 is the highest/)
    expect(note).not.toMatch(/1 the best/)
    const shaded = table.querySelector('td[data-shade] span') as HTMLElement
    expect(shaded.className).toContain('text-ink')
    expect(shaded.className).not.toContain('text-ink-3')
  })
})
