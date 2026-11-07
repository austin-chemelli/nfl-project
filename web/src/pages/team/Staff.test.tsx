import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import type { TeamFile } from '../../data/contract'
import car from '../../test/fixtures/site/team/CAR.json'
import lac from '../../test/fixtures/site/team/LAC.json'
import { Staff } from './Staff'

afterEach(cleanup)
const carFile = () => structuredClone(car) as unknown as TeamFile
const lacFile = () => structuredClone(lac) as unknown as TeamFile

describe('Staff tab', () => {
  it('CAR shows Idzik, his situation and the Week 9 change', () => {
    render(<Staff file={carFile()} />)
    expect(screen.getByText('Brad Idzik')).toBeInTheDocument()
    expect(screen.getByText('First year calling NFL plays, promoted from this staff')).toBeInTheDocument()
    expect(screen.getByText('Week 9: Todd Wash took over the defense from Ejiro Evero')).toBeInTheDocument()
    expect(screen.getAllByText('Brad Idzik')).toHaveLength(1)
    const link = screen.getAllByRole('link', { name: 'Team site' })[0]
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('an unconfirmed unit shows no source link and no situation', () => {
    const f = carFile()
    f.units.off.caller = { ...f.units.off.caller!, confirmed: false }
    render(<Staff file={f} />)
    expect(screen.getByText('Runs the offense')).toBeInTheDocument()
    expect(screen.getByText('Play-caller not confirmed')).toBeInTheDocument()
    expect(document.querySelector('a[href*="to-call-plays"]')).toBeNull()
    expect(screen.queryByText('First year calling NFL plays, promoted from this staff')).toBeNull()
  })

  it('says so when a unit has no caller', () => {
    const f = carFile()
    f.units.def.caller = null
    render(<Staff file={f} />)
    expect(screen.getByText('No one established')).toBeInTheDocument()
  })

  it('LAC has no changes heading', () => {
    render(<Staff file={lacFile()} />)
    expect(screen.queryByText('Changes this season')).toBeNull()
  })
})
