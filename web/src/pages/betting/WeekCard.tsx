import type { ReactNode } from 'react'
import { Card, Section } from '../../components/ui'
import type { BettingWeek, CardGame } from '../../data/contract'
import { stakeFor } from '../../lib/bankroll'
import { american, dollars, kickoffEt, pct } from '../../lib/format'
import { SHORT } from '../../lib/models'
import { Lede } from './common'
import { bookName, groupCard, stakePrice, toWin } from './weekFacts'

export type Draft = { game_id: string; side: 'home' | 'away'; price: number; stake: number | null }

const CHIP: Record<string, string> = {
  look: 'border-[var(--good)] text-[var(--good)]',
  fun: 'border-line text-ink-2',
}

function Chip({ verdict, label }: { verdict: string; label: string }) {
  return <span className={`inline-block rounded border px-1.5 py-px text-[11px] font-medium uppercase tracking-wide ${CHIP[verdict] ?? 'border-line text-ink-3'}`}>{label}</span>
}

function Fact({ children }: { children: ReactNode }) {
  return <li className="tabular">{children}</li>
}

function GameCard({ g, w, bankroll, onLog }: { g: CardGame; w: BettingWeek; bankroll: number | null; onLog?: (d: Draft) => void }) {
  const p = g.pick!
  const stake = stakeFor(bankroll, w.stake_pct)
  const price = stakePrice(g)
  return (
    <Card>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-semibold">{p.team} to win</h3>
        <Chip verdict={g.verdict!} label={g.verdict === 'look' ? 'Worth a look' : 'For fun'} />
      </div>
      <p className="mt-0.5 text-[13px] text-ink-3">
        {g.away} @ {g.home} · {kickoffEt(g.kickoff_utc)}
      </p>
      {g.reason && <p className="mt-2 text-[14px] text-ink-2">{g.reason}</p>}
      <ul className="mt-3 flex list-none flex-col gap-1 p-0 text-[14px]">
        <Fact>
          {SHORT[w.model] ?? w.model} {pct(p.p_model)}, market {pct(p.p_market)}
          {g.agree != null && <span className="text-ink-3"> · {g.agree} of 4 approaches pick {p.team}</span>}
        </Fact>
        {g.needed && (
          <>
            <Fact>
              <strong>Only at {american(g.needed.american)} or better</strong>
            </Fact>
            <Fact>
              On an exchange: {Math.floor(g.needed.cents)}¢ or less{' '}
              <span className="text-ink-3">(includes the taker fee, {pct(w.exchange_fee, 0)} × price × (1 − price))</span>
            </Fact>
          </>
        )}
        {g.best && (
          <Fact>
            Best licensed book now: {american(g.best.price)} ({bookName(g.best.book)})
            {g.clears === false && <span className="text-ink-3"> · worse than fair, as book prices nearly always are</span>}
          </Fact>
        )}
        <Fact>
          Stake: {stake != null ? dollars(stake) : `${pct(w.stake_pct, 0)} of your bankroll`}
          {price != null && (stake != null ? ` to win ${dollars(toWin(stake, price), 2)}` : ` · wins ${dollars(toWin(1, price), 2)} for every $1 staked`)}
        </Fact>
      </ul>
      {onLog && g.needed && (
        <button
          type="button"
          onClick={() => onLog({ game_id: g.game_id, side: p.side, price: g.needed!.american, stake })}
          className="mt-3 rounded border border-line px-3 py-1 text-[13px] text-ink hover:bg-surface-2"
        >
          Log this bet
        </button>
      )}
    </Card>
  )
}

function CompactList({ games }: { games: CardGame[] }) {
  return (
    <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[14px]">
      {games.map((g) => (
        <li key={g.game_id} className="border-b border-line pb-1">
          <span className="font-medium">{g.pick ? `${g.pick.team}` : `${g.away} @ ${g.home}`}</span>
          {g.pick && <span className="text-ink-3"> ({g.away} @ {g.home})</span>}
          {g.reason && <span className="text-ink-2"> · {g.reason}</span>}
        </li>
      ))}
    </ul>
  )
}

/** This week's games under the guide's rules. */
export function WeekCard({ w, bankroll, onLog }: { w: BettingWeek; bankroll: number | null; onLog?: (d: Draft) => void }) {
  const groups = groupCard(w.card.games)
  const unders = w.card.games.filter((g) => g.total)
  return (
    <div className="flex flex-col gap-8">
      <p className="text-[14px] text-ink-2">
        Singles only, no parlays. {pct(w.stake_pct, 0)} a bet. The model version: {w.model} {w.model_version}.
      </p>

      {groups.look.length > 0 && (
        <Section title="Worth a look">
          <Lede>The cheapest prices in our history, where the model agrees with the market or likes the pick more.</Lede>
          <div className="grid gap-3 lg:grid-cols-2">
            {groups.look.map((g) => (
              <GameCard key={g.game_id} g={g} w={w} bankroll={bankroll} onLog={onLog} />
            ))}
          </div>
        </Section>
      )}

      {groups.fun.length > 0 && (
        <Section title="For fun">
          <Lede>These cost about the cut; fine for fun at the same stake.</Lede>
          <div className="grid gap-3 lg:grid-cols-2">
            {groups.fun.map((g) => (
              <GameCard key={g.game_id} g={g} w={w} bankroll={bankroll} onLog={onLog} />
            ))}
          </div>
        </Section>
      )}

      {groups.skip.length > 0 && (
        <Section title="Skip">
          <Lede>The costliest prices in our history.</Lede>
          <CompactList games={groups.skip} />
        </Section>
      )}

      {groups.started.length > 0 && (
        <Section title="Started">
          <Lede>Already under way: the price is no longer on offer.</Lede>
          <CompactList games={groups.started} />
        </Section>
      )}

      {groups.none.length > 0 && (
        <Section title="No price yet">
          <Lede>No market price or no model number for these games yet.</Lede>
          <ul className="m-0 list-none p-0 text-[14px]">
            {groups.none.map((g) => (
              <li key={g.game_id} className="border-b border-line pb-1">
                {g.away} @ {g.home} <span className="text-ink-3">· {kickoffEt(g.kickoff_utc)}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title="Targeted: the under">
        {unders.length === 0 ? (
          <p className="text-[14px] text-ink-2">No targeted spread or total this week: no spread condition cleared the bar in our history, and the windy-under rule needs a 15+ mph forecast.</p>
        ) : (
          <div className="grid gap-3 lg:grid-cols-2">
            {unders.map((g) => {
              const t = g.total!
              return (
                <Card key={g.game_id}>
                  <h3 className="font-semibold">
                    {g.away} @ {g.home}: under {t.line ?? ''}
                  </h3>
                  <p className="mt-0.5 text-[13px] text-ink-3">Forecast wind {t.wind_mph} mph · {kickoffEt(g.kickoff_utc)}</p>
                  <p className="mt-2 text-[14px] text-ink-2">{t.reason}</p>
                  <ul className="mt-3 flex list-none flex-col gap-1 p-0 text-[14px]">
                    <Fact>
                      <strong>Only at {american(t.needed.american)} or better</strong>
                    </Fact>
                    {t.best && t.best.price != null && (
                      <Fact>
                        Best licensed book now: under {t.best.point ?? t.line} at {american(t.best.price)}
                        {t.best.book ? ` (${bookName(t.best.book)})` : ''}
                      </Fact>
                    )}
                  </ul>
                </Card>
              )
            })}
          </div>
        )}
      </Section>
    </div>
  )
}
