import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderRoute } from '../../test/render'

describe('Method page', () => {
  it('renders approach names, the locks link and data freshness', async () => {
    renderRoute('/method')
    expect(await screen.findByRole('heading', { level: 3, name: 'The Analyst' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3, name: 'The Traditionalist' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /browse the lock files/ })).toHaveAttribute('href', 'https://github.com/austin-chemelli/nfl-project/tree/main/public/predictions')
    // freshness is on the data tab
    await userEvent.click(screen.getByRole('tab', { name: 'Data' }))
    expect(await screen.findByText('2026-10-27 22:46 UTC')).toBeInTheDocument()
    expect(screen.getByText('pbp')).toBeInTheDocument()
  })

  it('has the null-rate audit behind a disclosure', async () => {
    renderRoute('/method?tab=data')
    expect(await screen.findByText(/Show the \d+ columns with the most missing values/)).toBeInTheDocument()
  })
})
