import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Help } from './Help'

const setup = () => {
  render(
    <div>
      <Help text="A tip">Label</Help>
      <button type="button">elsewhere</button>
    </div>,
  )
  const q = screen.getByRole('button', { name: 'What is this?' })
  const tip = () => screen.getByRole('tooltip', { hidden: true })
  return { q, open: () => !tip().className.split(' ').includes('hidden') }
}

describe('Help', () => {
  it('a tap (pointerdown, focus, click) opens it, and a second tap closes it', () => {
    const { q, open } = setup()
    fireEvent.pointerDown(q, { pointerType: 'touch' })
    fireEvent.focus(q)
    fireEvent.click(q)
    expect(open()).toBe(true)
    fireEvent.pointerDown(q, { pointerType: 'touch' })
    fireEvent.click(q)
    expect(open()).toBe(false)
  })

  it('a tap elsewhere closes it', () => {
    const { q, open } = setup()
    fireEvent.pointerDown(q, { pointerType: 'touch' })
    fireEvent.click(q)
    expect(open()).toBe(true)
    fireEvent.pointerDown(screen.getByRole('button', { name: 'elsewhere' }), { pointerType: 'touch' })
    expect(open()).toBe(false)
  })

  it('hover opens for a mouse only', () => {
    const { q, open } = setup()
    fireEvent.pointerEnter(q, { pointerType: 'touch' })
    expect(open()).toBe(false)
    fireEvent.pointerEnter(q, { pointerType: 'mouse' })
    expect(open()).toBe(true)
    fireEvent.pointerLeave(q, { pointerType: 'mouse' })
    expect(open()).toBe(false)
  })

  it('keyboard focus opens it and Escape closes it', async () => {
    const { q, open } = setup()
    await userEvent.tab()
    expect(q).toHaveFocus()
    expect(open()).toBe(true)
    await userEvent.keyboard('{Escape}')
    expect(open()).toBe(false)
  })

  it('stays on a phone screen wherever the "?" sits, and closes once its "?" scrolls away', () => {
    const { q, open } = setup()
    const tip = screen.getByRole('tooltip', { hidden: true })
    vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(390)
    vi.spyOn(q, 'getBoundingClientRect').mockReturnValue({ left: 150, top: 100, bottom: 116 } as DOMRect)
    fireEvent.click(q)
    expect(tip.style.left).toBe('94px') // 390 - 288 wide - 8 from the edge
    expect(tip.style.top).toBe('120px')
    vi.spyOn(q, 'getBoundingClientRect').mockReturnValue({ left: 150, top: 300, bottom: 316 } as DOMRect)
    fireEvent.scroll(window)
    expect(open()).toBe(true) // focus can scroll the page, so the tip follows its "?"
    expect(tip.style.top).toBe('320px')
    vi.spyOn(q, 'getBoundingClientRect').mockReturnValue({ left: 150, top: -40, bottom: -24 } as DOMRect)
    fireEvent.scroll(window)
    expect(open()).toBe(false)
    vi.restoreAllMocks()
  })
})
