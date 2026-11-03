import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FinePrint } from './FinePrint'

describe('FinePrint', () => {
  it('is a collapsed details labeled "Fine print"', async () => {
    const { container } = render(<FinePrint><p>Caveat one</p></FinePrint>)
    const d = container.querySelector('details')!
    expect(d.open).toBe(false)
    await userEvent.click(screen.getByText('Fine print'))
    expect(d.open).toBe(true)
    expect(screen.getByText('Caveat one')).toBeVisible()
  })
})
