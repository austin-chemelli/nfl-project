import { Link, useNavigate } from 'react-router'
import { Help } from '../../components/Help'
import { Card, Loaded, ModelBadge, ProbCell, Section, StatusBadge, TableScroll, td, th } from '../../components/ui'
import { isNotFound, useSlate } from '../../data/api'
import type { GameRow, Meta } from '../../data/contract'
import { ago, kickoffEt, pct, spreadLabel } from '../../lib/format'
import { approachOf } from '../../lib/meta'
import { colorVar } from '../../lib/models'
import { byKickoff, correct, disagreements, divergenceText, DIVERGE, gameStatus, neighbours, pickOf, weekHref, scoreText, sideText } from './helpers'

const COLS = ['traditionalist', 'analyst', 'sharp', 'student', 'ensemble'] as const

export function WeekView({ meta, season, week }: { meta: Meta; season: number; week: number }) {
  const q = useSlate(season, week)
  const lock = meta.last_lock
  return (
    <>
      <WeekPicker meta={meta} season={season} week={week} />
      <p className="-mt-4 text-[13px] text-ink-3">
        Site data updated {ago(meta.generated_at)}.{' '}
        {lock ? `Last lock: week ${lock.week}, ${kickoffEt(lock.lock_ts)}.` : 'No live lock yet.'}
      </p>
      {q.isError && isNotFound(q.error) ? (
        <Card>
          <div className="font-medium">No slate for {season} week {week} yet.</div>
          <p className="mt-1 text-ink-2">Pick another week above. Slates appear once the schedule for that week is published.</p>
        </Card>
      ) : (
        <Loaded q={q} what="slate">
          {(s) => <Games meta={meta} games={byKickoff(s.games)} week={week} />}
        </Loaded>
      )}
      <p className="text-[13px] text-ink-3">Probabilities are the models' estimates, not advice. Fan-made, not affiliated with the NFL.</p>
    </>
  )
}

function WeekPicker({ meta, season, week }: { meta: Meta; season: number; week: number }) {
  const nav = useNavigate()
  const { prev, next } = neighbours(meta.weeks, week)
  const go = (w: number | null) => w != null && nav(weekHref(meta, season, w))
  const btn = 'rounded-md border border-line bg-surface-1 px-3 py-1.5 text-[13px] enabled:hover:bg-surface-2 disabled:opacity-40'
  return (
    <div className="flex flex-wrap items-center gap-2">
      <button type="button" className={btn} disabled={prev == null} onClick={() => go(prev)} aria-label="Previous week">
        ← Prev
      </button>
      <label className="flex items-center gap-2 text-[13px] text-ink-2">
        <span>Week</span>
        <select
          className="rounded-md border border-line bg-surface-1 px-2 py-1.5 text-ink"
          value={week}
          onChange={(e) => go(Number(e.target.value))}
        >
          {meta.weeks.map((w) => (
            <option key={w} value={w}>
              Week {w}
              {season === meta.season && w === meta.current_week ? ' (current)' : ''}
            </option>
          ))}
        </select>
      </label>
      <button type="button" className={btn} disabled={next == null} onClick={() => go(next)} aria-label="Next week">
        Next →
      </button>
      <span className="text-[13px] text-ink-3">{season} season</span>
    </div>
  )
}

function Games({ meta, games, week }: { meta: Meta; games: GameRow[]; week: number }) {
  if (games.length === 0) return <Card>No games listed for week {week}.</Card>
  return (
    <>
      <Disagreements meta={meta} games={games} />
      <Section
        title={`Week ${week}`}
        help="One line per approach plus the average of all four. Each cell is the team that approach favors and its win chance."
      >
        <Legend />
        <div className="hidden md:block">
          <TableScroll>
            <GameTable meta={meta} games={games} />
          </TableScroll>
        </div>
        <div className="flex flex-col gap-3 md:hidden">
          {games.map((g) => (
            <GameCard key={g.game_id} meta={meta} g={g} />
          ))}
        </div>
      </Section>
    </>
  )
}

function Legend() {
  return (
    <p className="mb-3 max-w-3xl text-[13px] text-ink-2">
      Shaded cell with ▲/▼: the approach is {Math.round(DIVERGE * 100)}+ points more on the home (▲) or away (▼) side than the market. ✓/✗: right or
      wrong about the winner. <b>Preview</b> = scored now, not a lock; <b>locked</b> = recorded before kickoff; <b>backfill</b> = finished game
      scored after the fact by frozen models.
    </p>
  )
}

function Disagreements({ meta, games }: { meta: Meta; games: GameRow[] }) {
  const top = disagreements(games)
  if (!top.length) return null
  const name = (id: string) => approachOf(meta, id)?.name.replace(/^The /, '') ?? id
  return (
    <Section title="Where they disagree most" help="The games where the four approaches are furthest apart on the home team's chance.">
      <ul className="flex flex-col gap-1.5">
        {top.map((d) => (
          <li key={d.game.game_id}>
            <Link to={`/game/${d.game.game_id}`} className="font-medium text-accent hover:underline">
              {d.game.away} @ {d.game.home}
            </Link>
            : {name(d.hi)} {sideText(d.game, d.ps[d.hi])} vs {name(d.lo)} {sideText(d.game, d.ps[d.lo])}{' '}
            <span className="text-ink-3">({Math.round(100 * d.spread)} points apart)</span>
          </li>
        ))}
      </ul>
    </Section>
  )
}

/** One approach's pick with divergence and result markers. */
function PickCell({ g, mid }: { g: GameRow; mid: string }) {
  const pk = pickOf(g, mid)
  if (!pk) return <span className="text-ink-3">–</span>
  const big = pk.div != null && Math.abs(pk.div) >= DIVERGE
  const ok = correct(g, mid)
  return (
    <span
      className="inline-flex items-center gap-1 rounded px-1.5 py-0.5"
      style={big ? { background: `color-mix(in srgb, ${colorVar(mid)} 22%, transparent)`, fontWeight: 600 } : undefined}
    >
      <ProbCell pHome={pk.pHome} home={g.home} away={g.away} />
      {big && pk.div != null && (
        <span title={divergenceText(pk.div, g)} aria-label={divergenceText(pk.div, g)}>
          {pk.div > 0 ? '▲' : '▼'}
        </span>
      )}
      {ok != null && (
        <span title={ok ? 'Picked the winner' : 'Missed the winner'} aria-label={ok ? 'Picked the winner' : 'Missed the winner'}>
          {ok ? '✓' : '✗'}
        </span>
      )}
    </span>
  )
}

function StatusCell({ g }: { g: GameRow }) {
  const { status, lockTs } = gameStatus(g)
  return (
    <div className="flex flex-col items-start gap-0.5">
      <StatusBadge status={status} />
      {status === 'locked' && lockTs && <span className="text-[11px] text-ink-3">{kickoffEt(lockTs)}</span>}
      {g.result && <span className="text-[12px] text-ink-2">Final: {scoreText(g)}</span>}
    </div>
  )
}

function MarketCell({ g }: { g: GameRow }) {
  return (
    <>
      {spreadLabel(g.market?.spread_home, g.home, g.away)}
    </>
  )
}

function GameTable({ meta, games }: { meta: Meta; games: GameRow[] }) {
  return (
    <table className="w-full border-collapse text-[14px]">
      <thead>
        <tr>
          <th className={th}>Kickoff (ET)</th>
          <th className={th}>Game</th>
          <th className={th}><Help text="The betting market's spread: the favorite and how many points it is favored by.">Line</Help></th>
          <th className={th}><Help text="The market's favorite and its win chance, with the bookmaker's margin removed.">Market pick</Help></th>
          {COLS.map((c) => (
            <th key={c} className={th}>
              <Help text={c === 'ensemble' ? 'The average of the four approaches.' : approachOf(meta, c)?.blurb}>
                <ModelBadge modelId={c} />
              </Help>
            </th>
          ))}
          <th className={th}>Status</th>
        </tr>
      </thead>
      <tbody>
        {games.map((g) => (
          <tr key={g.game_id}>
            <td className={`${td} whitespace-nowrap`}>{kickoffEt(g.kickoff_utc).replace(' ET', '')}</td>
            <td className={td}>
              <Link to={`/game/${g.game_id}`} className="font-semibold text-accent hover:underline">
                {g.away} @ {g.home}
              </Link>
              <div className="text-[12px] text-ink-3">{g.away_qb ?? '–'} / {g.home_qb ?? '–'}</div>
            </td>
            <td className={`${td} whitespace-nowrap`}><MarketCell g={g} /></td>
            <td className={td}><ProbCell pHome={g.market?.p_home} home={g.home} away={g.away} /></td>
            {COLS.map((c) => (
              <td key={c} className={`${td} whitespace-nowrap`}><PickCell g={g} mid={c} /></td>
            ))}
            <td className={td}><StatusCell g={g} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function GameCard({ meta, g }: { meta: Meta; g: GameRow }) {
  return (
    <Card>
      <div className="flex items-baseline justify-between gap-2">
        <Link to={`/game/${g.game_id}`} className="text-lg font-semibold text-accent hover:underline">
          {g.away} @ {g.home}
        </Link>
        <span className="text-[12px] text-ink-3">{kickoffEt(g.kickoff_utc)}</span>
      </div>
      <div className="text-[12px] text-ink-3">{g.away_qb ?? '–'} / {g.home_qb ?? '–'}</div>
      <div className="mt-2 flex items-center justify-between text-[13px]">
        <span className="text-ink-2">
          Market: <MarketCell g={g} /> · <ProbCell pHome={g.market?.p_home} home={g.home} away={g.away} />
        </span>
        <StatusCell g={g} />
      </div>
      <ul className="mt-2 flex flex-col gap-1 border-t border-line pt-2 text-[14px]">
        {COLS.map((c) => (
          <li key={c} className="flex items-center justify-between gap-2">
            <Help text={c === 'ensemble' ? 'The average of the four approaches.' : approachOf(meta, c)?.blurb}>
              <ModelBadge modelId={c} />
            </Help>
            <PickCell g={g} mid={c} />
          </li>
        ))}
      </ul>
      <div className="mt-1 text-[12px] text-ink-3">Market home win {pct(g.market?.p_home)}</div>
    </Card>
  )
}
