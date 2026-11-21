import { Section } from '../../components/ui'
import type { BettingWeek, CardGame, CardSide } from '../../data/contract'
import { american, dash, pct } from '../../lib/format'
import { Lede } from './common'
import { kickoffShort } from './weekFacts'

function Pill({ team, s, fallback }: { team: string; s: CardSide | undefined; fallback: number | null | undefined }) {
  const price = s?.price ?? fallback
  const tone = s?.view === 'target' ? 'border-[var(--good)] text-[var(--good)]' : s?.view === 'avoid' ? 'border-[var(--critical)] text-[var(--critical)]' : 'border-line text-ink-2'
  return (
    <span className={`tabular inline-flex shrink-0 items-baseline gap-1 rounded-full border px-2 py-0.5 text-[13px] font-medium ${tone}`}>
      {team}
      <span className="text-[12px] font-normal">{price != null ? american(price) : dash}</span>
      {s?.view === 'target' && <span className="sr-only">target</span>}
      {s?.view === 'avoid' && <span className="sr-only">skip</span>}
    </span>
  )
}

/**
 * The market's split of the game: each team's share of the bar is its win chance, written inside
 * it (away on the left, home on the right). The dot is where the Student splits it, the same dot as
 * on the target cards.
 */
function SplitBar({ g, home }: { g: CardGame; home: CardSide | undefined }) {
  if (!home) return <span className="h-5 flex-1 rounded-full bg-[var(--band)]" aria-hidden="true" />
  const away = (1 - home.p_market) * 100
  const dot = Math.max(3, Math.min(97, (1 - home.p_model) * 100))
  const label = `Home win chance: market ${pct(home.p_market)}, Student ${pct(home.p_model)}`
  return (
    <span role="img" aria-label={label} title={`${g.away} ${pct(1 - home.p_market)} · ${g.home} ${pct(home.p_market)} by the market; the Student says ${g.home} ${pct(home.p_model)}`} className="relative block h-5 min-w-0 flex-1">
      <span aria-hidden="true" className="tabular absolute inset-0 flex overflow-hidden rounded-full text-[11px] font-medium leading-5">
        <span className="h-full overflow-hidden bg-[var(--series-market)]/35 pl-2 text-left text-ink" style={{ width: `${away}%` }}>
          {away >= 18 ? pct(1 - home.p_market) : ''}
        </span>
        <span className="h-full flex-1 overflow-hidden bg-[var(--band)] pr-2 text-right text-ink">
          {away <= 82 ? pct(home.p_market) : ''}
        </span>
      </span>
      <span aria-hidden="true" className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface-1 bg-[var(--series-student)] shadow" style={{ left: `${dot}%` }} data-game={g.game_id} />
    </span>
  )
}

/** What the bar means, once above the rows. */
function Key() {
  return (
    <div aria-hidden="true" className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-ink-3">
      <span className="flex items-center gap-1.5">
        <span className="tabular inline-flex h-3.5 w-14 overflow-hidden rounded-full text-[9px] leading-[14px]">
          <span className="w-2/5 bg-[var(--series-market)]/35" />
          <span className="flex-1 bg-[var(--band)]" />
        </span>
        Each team's win chance by the betting market (left = away, right = home)
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-3 w-3 rounded-full border-2 border-surface-1 bg-[var(--series-student)] shadow" />
        Where the Student would split it: on the color change = it agrees with the market; the farther off, the more it disagrees
      </span>
    </div>
  )
}

/** Every game of the week as one row: away pill, the market's split with the Student's tick, home pill. */
export function Slate({ w }: { w: BettingWeek }) {
  const games = [...w.card.games].sort((a, b) => a.kickoff_utc.localeCompare(b.kickoff_utc))
  return (
    <Section title="The slate">
      <Lede>Every game. Green = target, red = skip.</Lede>
      <Key />
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {games.map((g) => {
          const home = g.sides.find((s) => s.side === 'home')
          const away = g.sides.find((s) => s.side === 'away')
          return (
            <li key={g.game_id} aria-label={`${g.away} at ${g.home}`} className={g.started ? 'opacity-60' : ''}>
              <div className="mb-0.5 text-[12px] text-ink-3">{kickoffShort(g.kickoff_utc)}</div>
              <div className="flex items-center gap-2">
                <Pill team={g.away} s={away} fallback={g.market?.away_ml} />
                <SplitBar g={g} home={home} />
                <Pill team={g.home} s={home} fallback={g.market?.home_ml} />
              </div>
            </li>
          )
        })}
      </ul>
    </Section>
  )
}
