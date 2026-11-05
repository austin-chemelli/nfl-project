/** One matchup on the slate (ADR 0017): teams, kickoff or score, market line, the compact probability strip, one sentence. */
import { Link } from 'react-router'
import { ProbStrip } from '../../charts'
import { StatusBadge } from '../../components/ui'
import { TeamAccent } from '../../components/TeamAccent'
import type { GameRow, Meta } from '../../data/contract'
import { kickoffEt, pct, spreadLabel } from '../../lib/format'
import { APPROACHES, SHORT } from '../../lib/models'
import { matchupVars } from '../../lib/teamColors'
import { teamInfo } from '../../lib/teams'
import { cardSentence, contrastLine, gameStatus, whyLine } from './helpers'

function TeamCode({ team, color }: { team: string; color: string }) {
  return (
    <span className="inline-flex flex-col" title={teamInfo(team).name}>
      <span>{team}</span>
      <TeamAccent team={team} color={color} />
    </span>
  )
}

/** "Final 23–20" with the winner's score emphasized. */
function FinalScore({ g }: { g: GameRow }) {
  const r = g.result
  if (!r || r.home_score == null || r.away_score == null) return null
  const cls = (won: boolean) => (won ? 'font-semibold text-ink' : 'text-ink-3')
  return (
    <span className="tabular whitespace-nowrap text-[15px]" aria-label={`Final: ${g.away} ${r.away_score}, ${g.home} ${r.home_score}`}>
      <span className="mr-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-3">Final</span>
      <span className={cls(r.margin < 0)}>{r.away_score}</span>
      <span className="text-ink-3">–</span>
      <span className={cls(r.margin > 0)}>{r.home_score}</span>
    </span>
  )
}

/** `showStatus` is false when this card's status is the usual one for the week (said once above the grid). */
export function GameCard({ g, meta, showStatus }: { g: GameRow; meta: Meta; showStatus: boolean }) {
  const { status } = gameStatus(g)
  const mk = g.market?.p_home ?? null
  const models = APPROACHES.flatMap((id) => {
    const p = g.models[id]?.p_home
    return p == null ? [] : [{ id, label: SHORT[id], p }]
  })
  const fav = mk == null ? null : `${mk >= 0.5 ? g.home : g.away} ${pct(mk >= 0.5 ? mk : 1 - mk)}`
  const pregame = g.result == null
  const why = whyLine(g, meta)
  const contrast = contrastLine(g)
  return (
    <Link
      to={`/game/${g.game_id}`}
      data-matchup
      style={matchupVars(g.away, g.home)}
      className="relative flex min-w-0 flex-col gap-2 overflow-hidden rounded-lg border border-line bg-surface-1 p-3 pt-3.5 hover:bg-surface-2 hover:no-underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent)]"
    >
      <span aria-hidden className="absolute inset-x-0 top-0 h-[3px]" style={{ background: 'linear-gradient(90deg, var(--team-away) 50%, var(--team-home) 50%)' }} />
      <div className="flex items-start justify-between gap-2">
        <span className="inline-flex items-baseline gap-2 text-lg font-semibold text-ink">
          <TeamCode team={g.away} color="var(--team-away)" />
          <span className="text-ink-3">@</span>
          <TeamCode team={g.home} color="var(--team-home)" />
        </span>
        <span className="flex flex-col items-end gap-1 text-right">
          {g.result ? <FinalScore g={g} /> : <span className="text-[13px] text-ink-2">{kickoffEt(g.kickoff_utc)}</span>}
          {showStatus && <StatusBadge status={status} />}
        </span>
      </div>
      <div className="text-[13px] text-ink-2">
        {spreadLabel(g.market?.spread_home, g.home, g.away)}
        {g.market?.total != null && <span className="text-ink-3"> · total {g.market.total}</span>}
        {fav && <span className="text-ink-3"> · market {fav}</span>}
      </div>
      {why && <div className="text-[14px] text-ink">{why}</div>}
      {contrast && <div className="text-[13px] text-ink-2">{contrast}</div>}
      <div className={`flex items-center gap-2 text-[11px] text-ink-3 ${pregame ? 'border-t border-line pt-2' : ''}`}>
        <span>{g.away}</span>
        <div className="min-w-0 flex-1">
          <ProbStrip compact home={g.home} market={mk} models={models} />
        </div>
        <span>{g.home}</span>
      </div>
      <div className={pregame ? 'text-[12px] text-ink-3' : 'text-[14px] text-ink'}>{cardSentence(g)}</div>
    </Link>
  )
}
