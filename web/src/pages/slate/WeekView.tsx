import { Link, useLocation, useNavigate, useSearchParams } from 'react-router'
import { Help } from '../../components/Help'
import { FinePrint } from '../../components/FinePrint'
import { Card, Loaded, ModelBadge, ProbCell, Section, Segmented, StatusBadge, TableScroll, td, th } from '../../components/ui'
import { isNotFound, useSlate } from '../../data/api'
import type { GameRow, Meta } from '../../data/contract'
import { ago, kickoffEt, spreadLabel } from '../../lib/format'
import { approachOf } from '../../lib/meta'
import { APPROACHES, colorVar } from '../../lib/models'
import { GameCard } from './GameCard'
import { Recap } from './Recap'
import { correct, divergenceText, DIVERGE, gameStatus, neighbours, parseSort, pickOf, scoreText, SORTS, sortGames, weekHref, type SortKey } from './helpers'

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
      <Recap season={season} week={week} />
      {q.isError && isNotFound(q.error) ? (
        <Card>
          <div className="font-medium">No slate for {season} week {week} yet.</div>
          <p className="mt-1 text-ink-2">Pick another week above. Slates appear once the schedule for that week is published.</p>
        </Card>
      ) : (
        <Loaded q={q} what="slate">
          {(s) => <Games meta={meta} games={s.games} week={week} />}
        </Loaded>
      )}
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
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const sort = parseSort(params.get('sort'))
  const table = params.get('view') === 'table'
  if (games.length === 0) return <Card>No games listed for week {week}.</Card>
  const sorted = sortGames(games, sort)
  const anyFinal = games.some((g) => g.result != null)
  const options = SORTS.filter((o) => o.value !== 'upset' || anyFinal)
  const setSort = (v: SortKey) =>
    setParams((p) => {
      const n = new URLSearchParams(p)
      if (v === 'kickoff') n.delete('sort')
      else n.set('sort', v)
      return n
    }, { replace: true })
  const viewLink = new URLSearchParams(params)
  if (table) viewLink.delete('view')
  else viewLink.set('view', 'table')
  const statuses = games.map((g) => gameStatus(g).status)
  const common = mode(statuses)
  return (
    <>
      <Section
        title={`Week ${week}`}
        help="Each card is one game: the dots are the four approaches and their average, the gray line is the betting market."
        aside={
          <div className="flex flex-wrap items-center gap-3">
            <Segmented label="Sort games" value={options.some((o) => o.value === sort) ? sort : 'kickoff'} options={options} onChange={setSort} />
            <Link to={{ pathname: location.pathname, search: viewLink.toString() }} replace className="text-[13px] text-accent hover:underline">
              {table ? 'Show as cards' : 'Show as table'}
            </Link>
          </div>
        }
      >
        <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-ink-3">
          <span className="inline-flex items-center gap-1.5">
            <StatusBadge status={common} /> {statuses.every((s) => s === common) ? 'on every game' : 'on most games; the others are marked'}
          </span>
          {!table && <CardKey />}
        </div>
        {table ? (
          <TableScroll>
            <GameTable meta={meta} games={sorted} />
          </TableScroll>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {sorted.map((g) => (
              <GameCard key={g.game_id} g={g} meta={meta} showStatus={gameStatus(g).status !== common} />
            ))}
          </div>
        )}
      </Section>
      <FinePrint>
        <Legend />
        <p>Probabilities are the models' estimates, not advice. Fan-made, not affiliated with the NFL.</p>
      </FinePrint>
    </>
  )
}

function mode(xs: string[]): string {
  const counts = new Map<string, number>()
  for (const x of xs) counts.set(x, (counts.get(x) ?? 0) + 1)
  return [...counts.entries()].reduce((a, b) => (b[1] > a[1] ? b : a))[0]
}

/** The one key for every card's strip: dots are home win chance, left is the away side. */
function CardKey() {
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2.5 gap-y-1">
      {APPROACHES.map((c) => <ModelBadge key={c} modelId={c} />)}
      <span className="inline-flex items-center gap-1.5">
        <span aria-hidden className="inline-block h-3 w-0.5 bg-[var(--series-market)] opacity-60" /> Market
      </span>
      <span>· dots: left is the away side, right the home side</span>
    </span>
  )
}

function Legend() {
  return (
    <p className="max-w-3xl">
      Shaded cell with ▲/▼ (table view): the approach is {Math.round(DIVERGE * 100)}+ points more on the home (▲) or away (▼) side than the market. ✓/✗: right or
      wrong about the winner. <b>Preview</b> = scored now, not a lock; <b>locked</b> = recorded before kickoff; <b>not locked</b> = no lock was
      recorded, scored as of an hour before kickoff; <b>backfill</b> = finished game scored after the fact by frozen models; – = not scored yet.
      A card's sentence names the approach furthest from the market, or how the four split, or how they did once the game is final; an upset is a winner the market
      gave under 45%.
    </p>
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
          {APPROACHES.map((c) => (
            <th key={c} className={th}>
              <Help text={approachOf(meta, c)?.blurb}>
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
            {APPROACHES.map((c) => (
              <td key={c} className={`${td} whitespace-nowrap`}><PickCell g={g} mid={c} /></td>
            ))}
            <td className={td}><StatusCell g={g} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
