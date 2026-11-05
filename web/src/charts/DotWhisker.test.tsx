import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DotWhisker } from './DotWhisker'

vi.mock('./useWidth', () => ({ useWidth: () => [() => undefined, 600] }))

describe('DotWhisker', () => {
  it('keeps the marker on the scale when every row sits to one side of it', () => {
    render(<DotWhisker rows={[{ key: 'a', label: 'A', value: 0.05, lo: 0.04, hi: 0.06 }]} format={String} marker={{ value: -0.03, label: 'no edge' }} />)
    const x = Number(screen.getByText(/no edge/).getAttribute('x'))
    expect(x).toBeGreaterThanOrEqual(170)
  })
})
