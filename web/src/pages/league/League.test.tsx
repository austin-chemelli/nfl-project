import { screen, within } from '@testing-library/react'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { renderRoute } from '../../test/render'

describe('League page', () => {
  it('renders the Teams tab from teams.json and names the page', async () => {
    renderRoute('/league')
    expect(await screen.findByRole('tab', { name: 'Teams' })).toHaveAttribute('aria-selected', 'true')
    expect(document.title).toMatch(/^League/)
  })

  it('is in the nav, after This week', async () => {
    renderRoute('/league')
    const nav = await screen.findByRole('navigation')
    const links = within(nav).getAllByRole('link').map((a) => a.textContent)
    expect(links.indexOf('League')).toBe(links.indexOf('This week') + 1)
  })

  it('shows a plain card, not an error, before the file exists', async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'league-'))
    fs.mkdirSync(path.join(root, 'site'))
    renderRoute('/league', root)
    expect(await screen.findByText(/appear after the next data update/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
