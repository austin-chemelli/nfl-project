import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ErrorBox } from './ui'
import { DataError } from '../data/api'

describe('ErrorBox', () => {
  it('suggests a reload when the data no longer matches the loaded app', () => {
    render(<ErrorBox error={new DataError('site/slate_2026_08.json', 'unexpected shape: x', false, true)} />)
    expect(screen.getByText(/updated since this page was opened/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reload page' })).toBeInTheDocument()
  })

  it('offers a reload without the update hint for other errors', () => {
    render(<ErrorBox error={new DataError('site/slate_2026_08.json', 'HTTP 500')} />)
    expect(screen.queryByText(/updated since this page was opened/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reload page' })).toBeInTheDocument()
  })
})
