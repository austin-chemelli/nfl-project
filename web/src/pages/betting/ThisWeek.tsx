import type { ReactNode } from 'react'
import { Card, Section, TableScroll, td, th } from '../../components/ui'
import type { BettingWeek, CardGame, CardSide } from '../../data/contract'
import { stakeFor } from '../../lib/bankroll'
import { american, dash, dollars, kickoffEt, pct, signedPct } from '../../lib/format'
import { SHORT } from '../../lib/models'
import { Lede } from './common'
import { kickoffShort, stakePrice, toWin, type Draft } from './weekFacts'

const byKickoff = (a: CardGame, b: CardGame) => a.kickoff_utc.localeCompare(b.kickoff_utc)
const wholePts = (x: number) => String(Math.round(x * 100))

function Chip({ children, tone }: { children: ReactNode; tone: 'good' | 'bad' | 'plain' }) {
  const c = tone === 'good' ? 'border-[var(--good)] text-[var(--good)]' : tone === 'bad' ? 'border-[var(--critical)] text-[var(--critical)]' : 'border-line text-ink-2'
  return <span className={`inline-block rounded border px-1.5 py-px text-[11px] font-medium uppercase tracking-wide ${c}`}>{children}</span>
}

function Strategy({ w }: { w: BettingWeek }) {
  const r = w.rules
  const lim = r.limits
  return (
    <Card>
      <h3 className="font-semibold">How to call your shot</h3>
      <ol className="mt-2 flex list-decimal flex-col gap-1.5 pl-5 text-[14px]">
        <li>Pick a few games, and bet each one on its own: a parlay multiplies the book&apos;s cut.</li>
        <li className="tabular">
          Back a team the Student likes a little more than the market: {wholePts(lim.lean_min)} to {wholePts(lim.lean_max)} points of win chance. The best spot is an underdog at +120 to +185: {signedPct(r.lean_dog.roi)} on {r.lean_dog.n.toLocaleString('en-US')} bets since 2006.
        </li>
        <li className="tabular">
          Don&apos;t chase big disagreements: when the Student is {wholePts(lim.lean_max)}+ points above the market, the market has usually been right (it knows the late news): {signedPct(r.big_gap.roi_second)} since 2016.
        </li>
        <li className="tabular">
          Skip −120 to −185 favorites ({signedPct(r.mid_fav.roi)}) and anything at +185 or longer ({signedPct(r.long.roi)}).
        </li>
        <li>Only bet at the price needed or better, and stake {pct(w.stake_pct, 0)} of your bankroll a bet.</li>
      </ol>
      <p className="tabular mt-3 text-[13px] text-ink-3">
        Even the best spot returned only {signedPct(r.lean_dog.roi_2021_2025)} in 2021-2025, and betting the Student&apos;s pick in every game lost {pct(Math.abs(r.model_pick.roi ?? 0), 1)}. It&apos;s a fun test, not income.
      </p>
    </Card>
  )
}

function Fact({ children }: { children: ReactNode }) {
  return <li className="tabular">{children}</li>
}

function TargetCard({ g, s, w, bankroll, onLog }: { g: CardGame; s: CardSide; w: BettingWeek; bankroll: number | null; onLog?: (d: Draft) => void }) {
  const stake = stakeFor(bankroll, w.stake_pct)
  const price = stakePrice(s)
  const opp = s.side === 'home' ? g.away : g.home
  const best = s.why === 'lean_dog'
  return (
    <Card className={g.started ? 'opacity-60' : ''}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-semibold">
          {s.team} to beat {opp}
        </h3>
        <span className="flex gap-1.5">
          {best && <Chip tone="good">Best spot</Chip>}
          {g.started && <Chip tone="plain">Started</Chip>}
        </span>
      </div>
      <p className="mt-0.5 text-[13px] text-ink-3">{kickoffEt(g.kickoff_utc)}</p>
      <p className="mt-2 text-[14px] text-ink-2">{s.reason}</p>
      <ul className="mt-3 flex list-none flex-col gap-1 p-0 text-[14px]">
        <Fact>
          Price now: <strong>{s.price != null ? american(s.price) : dash}</strong>{' '}
          {s.clears != null && <Chip tone={s.clears ? 'good' : 'bad'}>{s.clears ? 'Price is good' : 'Price too short'}</Chip>}
        </Fact>
        <Fact>
          {SHORT[w.model] ?? w.model} {pct(s.p_model)} · market {pct(s.p_market)}
        </Fact>
        <Fact>
          <strong>Only at {american(s.needed.american)} or better</strong>
          <span className="text-ink-3"> · on an exchange, {Math.floor(s.needed.cents)}¢ or less</span>
        </Fact>
        <Fact>
          Stake: {stake != null ? dollars(stake) : `${pct(w.stake_pct, 0)} of your bankroll`}
          {price != null && (stake != null ? ` to win ${dollars(toWin(stake, price), 2)}` : ` · wins ${dollars(toWin(1, price), 2)} for every $1 staked`)}
        </Fact>
      </ul>
      {onLog && !g.started && (
        <button
          type="button"
          onClick={() => onLog({ game_id: g.game_id, side: s.side, price: s.price ?? s.needed.american, stake })}
          className="mt-3 rounded border border-line px-3 py-1 text-[13px] text-ink hover:bg-surface-2"
        >
          Log this bet
        </button>
      )}
    </Card>
  )
}

function TotalCard({ g }: { g: CardGame }) {
  const t = g.total!
  return (
    <Card className={g.started ? 'opacity-60' : ''}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-semibold">
          Under {t.line ?? ''}: {g.away} @ {g.home}
        </h3>
        {g.started && <Chip tone="plain">Started</Chip>}
      </div>
      <p className="mt-0.5 text-[13px] text-ink-3">Forecast wind {t.wind_mph} mph · {kickoffEt(g.kickoff_utc)}</p>
      <p className="mt-2 text-[14px] text-ink-2">{t.reason}</p>
      <ul className="mt-3 flex list-none flex-col gap-1 p-0 text-[14px]">
        <Fact>
          <strong>Only at {american(t.needed.american)} or better</strong>
        </Fact>
      </ul>
    </Card>
  )
}

function Targets({ w, bankroll, onLog }: { w: BettingWeek; bankroll: number | null; onLog?: (d: Draft) => void }) {
  const games = [...w.card.games].sort(byKickoff)
  const sides = games.flatMap((g) => g.sides.filter((s) => s.view === 'target').map((s) => ({ g, s })))
  const totals = games.filter((g) => g.total)
  return (
    <Section title="Targeted bets" help="Sides where the Student likes a team a little more than the market, in the price ranges that have held up in history, plus windy-weather unders.">
      <Lede>At most {w.max_targets} a week, each on its own at the price needed or better.</Lede>
      {sides.length === 0 && totals.length === 0 ? (
        <p className="text-[14px] text-ink-2">Nothing fits this week. Sitting out is a fine bet.</p>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {sides.map(({ g, s }) => (
            <TargetCard key={`${g.game_id}-${s.side}`} g={g} s={s} w={w} bankroll={bankroll} onLog={onLog} />
          ))}
          {totals.map((g) => (
            <TotalCard key={`${g.game_id}-total`} g={g} />
          ))}
        </div>
      )}
    </Section>
  )
}

function StayAway({ w }: { w: BettingWeek }) {
  const lean = w.rules.limits.lean_min
  const rows = [...w.card.games]
    .sort(byKickoff)
    .filter((g) => !g.started)
    .flatMap((g) => g.sides.filter((s) => s.view === 'avoid' && (s.model_pick || s.gap >= lean)).map((s) => ({ g, s })))
  if (rows.length === 0) return null
  return (
    <Section title="Stay away" help="Sides that can look tempting, because the Student picks them or likes them more than the market, but sit in a price range or a gap that has cost money.">
      <Lede>These look tempting. History says they cost more than the cut.</Lede>
      <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[14px]">
        {rows.map(({ g, s }) => (
          <li key={`${g.game_id}-${s.side}`} className="border-b border-line pb-1">
            <span className="font-medium">{s.team}</span>
            <span className="tabular text-ink-3"> {s.price != null ? american(s.price) : dash}</span>
            <span className="text-ink-2"> · {s.reason}</span>
          </li>
        ))}
      </ul>
    </Section>
  )
}

function TeamCell({ s, team, fallback }: { s: CardSide | undefined; team: string; fallback: number | null | undefined }) {
  const price = s?.price ?? fallback
  const tag = s?.view === 'target' ? <Chip tone="good">Target</Chip> : s?.view === 'avoid' ? <Chip tone="bad">Avoid</Chip> : null
  return (
    <td className={td}>
      <span className="font-medium">{team}</span> <span className="tabular text-ink-2">{price != null ? american(price) : dash}</span> {tag}
    </td>
  )
}

function Slate({ w }: { w: BettingWeek }) {
  const games = [...w.card.games].sort(byKickoff)
  return (
    <Section title="The whole slate">
      <Lede>Every game, both teams. Untagged sides cost about the cut ({signedPct(w.rules.no_view.roi)}).</Lede>
      <TableScroll>
        <table className="w-full text-[13px]">
          <thead>
            <tr>
              <th className={th}>Kickoff</th>
              <th className={th}>Away</th>
              <th className={th}>Home</th>
              <th className={th}>Home win chance: Student / market</th>
            </tr>
          </thead>
          <tbody>
            {games.map((g) => {
              const home = g.sides.find((s) => s.side === 'home')
              const away = g.sides.find((s) => s.side === 'away')
              return (
                <tr key={g.game_id} className={g.started ? 'opacity-60' : ''}>
                  <td className={`${td} whitespace-nowrap`}>{kickoffShort(g.kickoff_utc)}</td>
                  <TeamCell s={away} team={g.away} fallback={g.market?.away_ml} />
                  <TeamCell s={home} team={g.home} fallback={g.market?.home_ml} />
                  <td className={`${td} tabular whitespace-nowrap`}>{home ? `${pct(home.p_model)} / ${pct(home.p_market)}` : dash}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </TableScroll>
    </Section>
  )
}

/** This week's slate: a few targeted bets, the ones to stay away from, and every game. */
export function ThisWeek({ w, bankroll, onLog }: { w: BettingWeek; bankroll: number | null; onLog?: (d: Draft) => void }) {
  return (
    <div className="flex flex-col gap-8">
      <p className="text-[13px] text-ink-3">
        Model version: {SHORT[w.model] ?? w.model} {w.model_version ?? ''}.
      </p>
      <Strategy w={w} />
      <Targets w={w} bankroll={bankroll} onLog={onLog} />
      <StayAway w={w} />
      <Slate w={w} />
    </div>
  )
}
