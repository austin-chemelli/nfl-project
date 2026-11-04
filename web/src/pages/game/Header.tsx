/** The game page's title and one quiet line of facts (ADR 0017); the final score is the only loud element. */
import { StatusBadge } from '../../components/ui'
import { TeamAccent } from '../../components/TeamAccent'
import type { Game } from '../../data/contract'
import { kickoffEt } from '../../lib/format'
import { teamInfo } from '../../lib/teams'
import { gameStatus } from '../slate/helpers'

/** "CAR @ GB" with a team-color bar under each code; works from the id alone, before the data arrives. */
export function GameTitle({ away, home }: { away: string; home: string }) {
  return (
    <span className="inline-flex items-baseline gap-2">
      <TeamCode team={away} />
      <span className="text-ink-3">@</span>
      <TeamCode team={home} />
    </span>
  )
}

function TeamCode({ team }: { team: string }) {
  return (
    <span className="inline-flex flex-col" title={teamInfo(team).name}>
      <span>{team}</span>
      <TeamAccent team={team} />
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

function Score({ team, pts, won }: { team: string; pts: number; won: boolean }) {
  return (
    <span className={won ? 'text-ink' : 'text-ink-3'}>
      {team} {pts}
    </span>
  )
}
