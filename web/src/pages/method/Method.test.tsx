import { describe, expect, it } from 'vitest'
import { screen, within } from '@testing-library/react'
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

  it('has no "Leans on" line for the Student, and a minus note on cards with a negative share', async () => {
    renderRoute('/method')
    const card = async (name: string) => (await screen.findByRole('heading', { level: 3, name })).closest('div') as HTMLElement
    const student = await card('The Student')
    expect(within(student).queryByText(/Leans on/)).toBeNull()
    const sharp = await card('The Sharp')
    expect(within(sharp).getByText(/Leans on/)).toBeInTheDocument()
    expect(within(sharp).getByText('Sizes add up to 100, ignoring signs. A minus means it leans against that group.')).toBeInTheDocument()
    expect(within(sharp).getByText('−5')).toBeInTheDocument()
    expect(within(await card('The Analyst')).queryByText(/ignoring signs/)).toBeNull()
  })
})
