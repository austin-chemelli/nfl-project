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

/** The market's split of the game (away share in the away color, home share in the home color) with the Student's chance as a tick. */
function SplitBar({ g, home }: { g: CardGame; home: CardSide | undefined }) {
  if (!home) return <span className="h-3 flex-1 rounded-full bg-[var(--band)]" aria-hidden="true" />
  const away = (1 - home.p_market) * 100
  const tick = (1 - home.p_model) * 100
  const label = `Home win chance: market ${pct(home.p_market)}, Student ${pct(home.p_model)}`
  return (
    <span role="img" aria-label={label} title={label} className="relative block h-4 min-w-0 flex-1">
      <span className="absolute inset-x-0 top-1/2 flex h-2.5 -translate-y-1/2 overflow-hidden rounded-full">
        <span className="h-full bg-[var(--band)]" style={{ width: `${away}%` }} />
        <span className="h-full flex-1 bg-ink-3/45" />
      </span>
      <span aria-hidden="true" className="absolute top-0 h-4 w-1 -translate-x-1/2 rounded-sm border border-surface-1 bg-ink" style={{ left: `${tick}%` }} data-game={g.game_id} />
    </span>
  )
}

/** Every game of the week as one row: away pill, the market's split with the Student's tick, home pill. */
export function Slate({ w }: { w: BettingWeek }) {
  const games = [...w.card.games].sort((a, b) => a.kickoff_utc.localeCompare(b.kickoff_utc))
  return (
    <Section title="The slate">
      <Lede>Every game. Green = target, red = skip.</Lede>
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
