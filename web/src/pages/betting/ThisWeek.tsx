import { useId } from 'react'
import { Help } from '../../components/Help'
import { SummaryStrip, Tile } from '../../components/SummaryStrip'
import { Section } from '../../components/ui'
import type { BettingWeek } from '../../data/contract'
import { american, dash, dollars, pct, signedPct } from '../../lib/format'
import { stakeFor } from '../../lib/bankroll'
import { BankrollInput } from './BankrollInput'
import { Lede } from './common'
import { Slate } from './Slate'
import { TargetCard, TotalCard } from './TargetCards'
import { stayAway, targetsOf, type Draft } from './weekFacts'

function Rule({ ok, label, tip }: { ok: boolean; label: string; tip: string }) {
  return (
    <li className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-[13px] ${ok ? 'border-line text-ink' : 'border-[var(--critical)] text-ink'}`}>
      <span aria-hidden="true" className={`font-bold ${ok ? 'text-[var(--good)]' : 'text-[var(--critical)]'}`}>
        {ok ? '✓' : '✕'}
      </span>
      <span className="sr-only">{ok ? 'Do: ' : "Don't: "}</span>
      <Help text={tip}>{label}</Help>
    </li>
  )
}

function HouseRules({ w }: { w: BettingWeek }) {
  const r = w.rules
  return (
    <ul aria-label="House rules" className="m-0 flex list-none flex-wrap gap-2 p-0">
      <Rule ok label="Singles" tip="A parlay multiplies the book's cut on every leg. Bet each game on its own." />
      <Rule ok label={`${pct(w.stake_pct, 0)} a bet`} tip={`Stake ${pct(w.stake_pct, 0)} of your bankroll on each bet, so a bad week can't sink you.`} />
      <Rule ok label="Price shown or better" tip="Each card shows the worst price still worth taking. At a worse price, skip it." />
      <Rule
        ok={false}
        label="No −120 to −185, no long shots"
        tip={`Favorites from −120 to −185 returned ${signedPct(r.mid_fav.roi)} a bet since 2006; long shots (+185 or longer) ${signedPct(r.long.roi)}.`}
      />
    </ul>
  )
}

function StayAway({ w }: { w: BettingWeek }) {
  const rows = stayAway(w)
  const id = useId()
  if (rows.length === 0) return null
  return (
    <Section title="Stay away">
      <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
        {rows.map(({ g, s }) => {
          const d = `${id}-${g.game_id}-${s.side}`
          return (
            <li key={d} title={s.reason} className="rounded-full border border-[var(--critical)] px-3 py-1 text-[13px]">
              <span aria-describedby={d}>
                <span className="font-semibold">{s.team}</span>
                <span className="tabular text-ink-2"> {s.price != null ? american(s.price) : dash}</span>
                <span className="text-ink-2"> · {s.label ?? 'Skip'}</span>
              </span>
              <span id={d} className="sr-only">
                {s.reason}
              </span>
            </li>
          )
        })}
      </ul>
    </Section>
  )
}

function Targets({ w, bankroll, onLog }: { w: BettingWeek; bankroll: number | null; onLog?: (d: Draft) => void }) {
  const sides = targetsOf(w)
  const totals = w.card.games.filter((g) => g.total)
  return (
    <Section title="Targets">
      <Lede>Best first, by how bets like them did since 2006.</Lede>
      {sides.length === 0 && totals.length === 0 ? (
        <p className="text-[14px] text-ink-2">Nothing clears the bar this week. Sitting out is a fine bet.</p>
      ) : (
        <ul className="m-0 grid list-none gap-3 p-0 md:grid-cols-2 lg:grid-cols-3">
          {sides.map(({ g, s }, i) => (
            <TargetCard key={`${g.game_id}-${s.side}`} w={w} g={g} s={s} rank={i + 1} bankroll={bankroll} onLog={onLog} />
          ))}
          {totals.map((g) => (
            <TotalCard key={`${g.game_id}-total`} g={g} />
          ))}
        </ul>
      )}
    </Section>
  )
}

/** This week: the targets with their grades, what to skip, and every game as a picture. */
export function ThisWeek({ w, bankroll, onLog }: { w: BettingWeek; bankroll: number | null; onLog?: (d: Draft) => void }) {
  const targets = targetsOf(w).length + w.card.games.filter((g) => g.total).length
  const stake = stakeFor(bankroll, w.stake_pct)
  return (
    <div className="flex flex-col gap-8">
      <SummaryStrip>
        <Tile label="Targets" value={targets} accent="var(--good)" />
        <Tile label="Stay away" value={stayAway(w).length} accent="var(--critical)" />
        <Tile label="Your stake" value={<BankrollInput />} sub={stake != null ? `${dollars(stake)} a bet` : `${pct(w.stake_pct, 0)} of your bankroll`} />
      </SummaryStrip>
      <HouseRules w={w} />
      <Targets w={w} bankroll={bankroll} onLog={onLog} />
      <StayAway w={w} />
      <Slate w={w} />
    </div>
  )
}
