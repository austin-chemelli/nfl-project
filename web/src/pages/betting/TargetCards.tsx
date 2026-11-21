import type { ReactNode } from 'react'
import { Help } from '../../components/Help'
import { TeamAccent } from '../../components/TeamAccent'
import type { BettingWeek, CardGame, CardSide } from '../../data/contract'
import { stakeFor } from '../../lib/bankroll'
import { american, dash, dollars, pct } from '../../lib/format'
import { matchupVars } from '../../lib/teamColors'
import { ChanceBar } from './ChanceBar'
import { GRADE_TONE, kickoffShort, stakePrice, toWin, type Draft } from './weekFacts'

/** The price now as an exchange contract price in cents (its implied chance, cut included). */
const exchangeCents = (a: number) => Math.round(100 / (a > 0 ? 1 + a / 100 : 1 + 100 / -a))

/** A circle with the grade; `tip` says how bets like this have done. */
function GradeBadge({ grade, tip }: { grade: string; tip: string }) {
  return (
    <Help text={tip}>
      <span role="img" aria-label={`Grade ${grade}`} className={`inline-flex h-9 w-9 items-center justify-center rounded-full border-2 text-base font-bold ${GRADE_TONE[grade] ?? GRADE_TONE.C}`}>
        {grade}
      </span>
    </Help>
  )
}

function gradeTip(w: BettingWeek, s: CardSide): string {
  const c = w.rules.cells?.find((x) => x.band === s.band && x.cell === s.cell)
  if (c && c.roi != null) return `How bets like this have done since 2006: ${c.roi >= 0 ? 'won' : 'lost'} ${pct(Math.abs(c.roi), 1)} a bet over ${c.n.toLocaleString('en-US')} bets.`
  return s.reason
}

function Frame({ g, side, rank, started, children }: { g: CardGame; side: 'home' | 'away' | null; rank: number | null; started: boolean; children: ReactNode }) {
  return (
    <li data-matchup style={matchupVars(g.away, g.home)} className={`list-none rounded-lg border border-line bg-surface-1 p-4 ${started ? 'opacity-60' : ''}`}>
      <TeamAccent team={side === 'home' ? g.home : g.away} color={side == null ? 'var(--accent)' : `var(--team-${side})`} className="mb-3" />
      <div data-rank={rank ?? undefined}>{children}</div>
    </li>
  )
}

function Started() {
  return <span className="rounded border border-line px-1.5 py-px text-[11px] font-medium uppercase tracking-wide text-ink-3">Started</span>
}

const Rank = ({ n }: { n: number }) => <span className="tabular text-[13px] font-semibold text-ink-3">#{n}</span>

export function TargetCard({ w, g, s, rank, bankroll, onLog }: { w: BettingWeek; g: CardGame; s: CardSide; rank: number; bankroll: number | null; onLog?: (d: Draft) => void }) {
  const stake = stakeFor(bankroll, w.stake_pct)
  const price = stakePrice(s)
  const opp = s.side === 'home' ? g.away : g.home
  const win = stake != null && price != null ? toWin(stake, price) : null
  return (
    <Frame g={g} side={s.side} rank={rank} started={g.started}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Rank n={rank} />
            {g.started && <Started />}
          </div>
          <h3 className="text-3xl font-bold leading-tight tracking-tight">
            {s.team} <span className="text-[15px] font-medium text-ink-2">{s.side === 'home' ? 'vs' : '@'} {opp}</span>
          </h3>
          <p className="text-[13px] text-ink-3">{kickoffShort(g.kickoff_utc)}</p>
        </div>
        {s.grade && <GradeBadge grade={s.grade} tip={gradeTip(w, s)} />}
      </div>
      <p className="mt-1 text-[14px] font-medium text-ink-2">
        <Help text={s.reason}>{s.label ?? 'Target'}</Help>
      </p>
      <div className="mt-3">
        <ChanceBar market={s.p_market} student={s.p_model} />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="tabular text-xl font-semibold" aria-label={`Price now ${s.price != null ? american(s.price) : 'unavailable'}`}>
          {s.price != null ? american(s.price) : dash}
        </span>
      </div>
      {s.price != null && (
        <p className="tabular mt-1 text-[12px] text-ink-3" title={`Fair price with the book's cut removed: ${american(s.needed.american)}`}>
          about {exchangeCents(s.price)}¢ on an exchange · don&apos;t take worse
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <span className="tabular text-[14px] text-ink-2">{stake != null && win != null ? `${dollars(stake)} → wins ${dollars(win, win % 1 === 0 ? 0 : 2)}` : ''}</span>
        {onLog && !g.started && (
          <button
            type="button"
            onClick={() => onLog({ game_id: g.game_id, side: s.side, price: s.price ?? s.needed.american, stake })}
            className="rounded border border-line px-3 py-1 text-[13px] text-ink hover:bg-surface-2"
          >
            Log bet
          </button>
        )}
      </div>
    </Frame>
  )
}

function Wind() {
  return (
    <svg width="18" height="14" viewBox="0 0 18 14" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <path d="M1 4h9a2.5 2.5 0 1 0-2.5-2.5M1 8h13a2.5 2.5 0 1 1-2.5 2.5M1 12h6" />
    </svg>
  )
}

export function TotalCard({ g }: { g: CardGame }) {
  const t = g.total!
  return (
    <Frame g={g} side={null} rank={null} started={g.started}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-semibold text-ink-3">{g.away} @ {g.home}</span>
            {g.started && <Started />}
          </div>
          <h3 className="text-3xl font-bold leading-tight tracking-tight">Under {t.line ?? ''}</h3>
          <p className="text-[13px] text-ink-3">{kickoffShort(g.kickoff_utc)}</p>
        </div>
        <GradeBadge grade="A" tip={t.reason} />
      </div>
      <p className="mt-1 text-[14px] font-medium text-ink-2">
        <Help text={t.reason}>{t.label ?? 'Windy under'}</Help>
      </p>
      <p className="tabular mt-3 flex items-center gap-1.5 text-xl font-semibold">
        <Wind />
        {t.wind_mph} mph
      </p>
      <p className="tabular mt-1 text-[12px] text-ink-3">bet at {american(t.needed.american)} or better</p>
    </Frame>
  )
}
