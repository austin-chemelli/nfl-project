import { useState } from 'react'
import { Link } from 'react-router'
import type { SimilarFile } from '../../data/contract'
import { SimilarView } from '../league/Similar'

/** The team page's Similar seasons tab: the League tab's view for this team, without the team picker (its flag cards are on the Overview). */
export function TeamSimilar({ code, sim }: { code: string; sim: SimilarFile }) {
  const [active, setActive] = useState<number | null>(null)
  const entry = Object.hasOwn(sim.teams, code) ? sim.teams[code] : null
  return (
    <div className="flex min-w-0 flex-col gap-4 text-[13px]">
      <p className="m-0 text-ink-2">
        {entry ? `Past teams that looked like ${code} after ${entry.games_played} games, and how they finished. ` : ''}History, not a forecast: the playoff odds are on the{' '}
        <Link to={{ search: '?tab=overview' }}>Overview</Link>. Other teams:{' '}
        <Link to={`/league?tab=similar&team=${code}`}>League, Similar seasons</Link>.
      </p>
      <SimilarView team={code} sim={sim} active={active} onActive={setActive} flags={false} />
    </div>
  )
}
