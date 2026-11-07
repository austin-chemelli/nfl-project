import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { TeamLink } from './TeamLink'

describe('TeamLink', () => {
  it('links a code, old franchise codes to the current one', () => {
    render(<MemoryRouter><TeamLink team="KC" /> <TeamLink team="OAK">Raiders</TeamLink></MemoryRouter>)
    expect(screen.getByRole('link', { name: 'KC' })).toHaveAttribute('href', '/team/KC')
    expect(screen.getByRole('link', { name: 'Raiders' })).toHaveAttribute('href', '/team/LV')
  })
  it('leaves an unknown code as text', () => {
    render(<MemoryRouter><TeamLink team="XYZ" /></MemoryRouter>)
    expect(screen.queryByRole('link')).toBeNull()
    expect(screen.getByText('XYZ')).toBeInTheDocument()
  })
})
