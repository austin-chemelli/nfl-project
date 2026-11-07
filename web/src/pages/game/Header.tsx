/** The game page's title and one quiet line of facts (ADR 0017); the final score is the only loud element. */
import type { ReactNode } from 'react'
import { StatusBadge } from '../../components/ui'
import { TeamAccent } from '../../components/TeamAccent'
import type { Game } from '../../data/contract'
import { kickoffEt } from '../../lib/format'
import { teamInfo } from '../../lib/teams'
import { gameStatus } from '../slate/helpers'
import { TeamLink } from '../../components/TeamLink'

/** The matchup as a banner: each team's color washing in from its own side. Works from the id alone, before the data arrives. */
export function GameTitle({ away, home }: { away: string; home: string }) {
  return (
    <span className="matchup-wash flex items-center justify-between gap-3 rounded-xl border border-line px-4 py-4 sm:px-6">
      <TeamSide team={away} color="var(--team-away)" />
      <span className="text-lg font-normal text-ink-3">@</span>
      <TeamSide team={home} color="var(--team-home)" right />
    </span>
  )
}

function TeamSide({ team, color, right = false }: { team: string; color: string; right?: boolean }) {
  return (
    <span className={`flex min-w-0 flex-col gap-1 ${right ? 'items-end text-right' : ''}`} title={teamInfo(team).name}>
      <TeamLink team={team} className="text-3xl font-bold leading-none text-ink no-underline hover:underline">{team}</TeamLink>
      <TeamAccent team={team} color={color} className="!w-14" />
      <TeamLink team={team} tabIndex={-1} className="hidden text-[13px] font-normal tracking-normal text-ink-2 sm:block">{teamInfo(team).name}</TeamLink>
    </span>
  )
}

export function GameHeader({ g }: { g: Game }) {
  const { status } = gameStatus(g)
  const facts = [
    kickoffEt(g.kickoff_utc),
    g.stadium ? `${g.stadium}${g.roof ? ` (${g.roof})` : ''}` : null,
    g.neutral_site ? 'neutral site' : null,
    `QBs ${g.away_qb ?? 'n/a'} / ${g.home_qb ?? 'n/a'}`,
  ].filter(Boolean)
  const r = g.result
  return (
    <div className="-mt-4 flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-ink-3">
        <span>{facts.join(' · ')}</span>
        <StatusBadge status={status} />
      </div>
      {r && r.home_score != null && r.away_score != null && (
        <div className="flex items-baseline gap-3 text-2xl font-semibold tabular" aria-label={`Final: ${g.away} ${r.away_score}, ${g.home} ${r.home_score}`}>
          <span className="text-[12px] font-medium uppercase tracking-wide text-ink-3">Final</span>
          <Score team={g.away} pts={r.away_score} won={r.margin < 0} />
          <span className="text-ink-3">–</span>
          <Score team={g.home} pts={r.home_score} won={r.margin > 0} />
        </div>
      )}
    </div>
  )
}

/** The one line that stays on screen down a finished game's page: the score and the result tile's verdict. */
export function PinnedResult({ g, verdict, ot }: { g: Game; verdict: ReactNode; ot: boolean }) {
  const r = g.result
  if (!r || r.home_score == null || r.away_score == null) return null
  return (
    <>
      <span className="tabular font-semibold">
        <Score team={g.away} pts={r.away_score} won={r.margin < 0} />
        <span className="text-ink-3"> – </span>
        <Score team={g.home} pts={r.home_score} won={r.margin > 0} />
      </span>
      {ot && <span className="text-[12px] text-ink-3">OT</span>}
      <span className="ml-auto truncate rounded-full border border-line px-2 py-px text-[12px] text-ink-2">{verdict}</span>
    </>
  )
}

function Score({ team, pts, won }: { team: string; pts: number; won: boolean }) {
  return (
    <span className={won ? 'text-ink' : 'text-ink-3'}>
      {team} {pts}
    </span>
  )
}
