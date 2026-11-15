import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { RoomGrade, type TeamHealth } from '../../data/contract'
import { roomsLede } from '../../lib/health'
import { Rooms } from './Rooms'

afterEach(cleanup)

const room = (o: Partial<RoomGrade>) => RoomGrade.parse({ grp: 'QB', rank: 10, label: 'good', z: 0.5, now_rank: 10, now_label: 'good', ...o })
const rooms = [
  room({ grp: 'WR', rank: 2, label: 'elite', basis: 'players', plays: 426, health: 0.25, now_rank: 24, now_label: 'average', stats: [{ key: 'wr_epa', label: 'EPA per target', value: 0.41, rank: 7 }] }),
  room({ grp: 'QB', rank: 7, now_rank: 7 }),
]

describe('Rooms', () => {
  it('orders rooms like the field, with the full rank and the estimate now', () => {
    render(<Rooms rooms={rooms} h={{ groups: [], starters: [] } as unknown as TeamHealth['now']} />)
    const items = [...screen.getByTestId('health-rooms').querySelectorAll('[data-room]')]
    expect(items.map((li) => li.getAttribute('data-room'))).toEqual(['QB', 'WR'])
    expect(items[1].textContent).toContain('~#24#2')
    expect(items[1].querySelector('[data-full]')).not.toBeNull()
    expect(items[0].querySelector('[data-full]')).toBeNull()
    expect(items[0].textContent).toContain('#7#7')
  })

  it('names the biggest drop', () => {
    expect(roomsLede(rooms)).toBe('Biggest drop: receivers, #2 at full strength to about #24 now.')
    expect(roomsLede([rooms[1]])).toMatch(/No room is missing enough/)
  })
})
