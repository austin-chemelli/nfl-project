/**
 * Where a team has the edge (ADR 0028, M25; both teams since 2026-11-12): up to four levers, each a battle
 * where this team's unit ranks well and the opponent's matching unit ranks poorly, with the history of teams
 * in its role (underdogs, favorites, or both sides of close games for a pick'em): how often they won overall
 * and when they won that battle. Conditions that aren't its edge are grey chips. Context, never a forecast:
 * no probability for the game appears here, and every number is read from the JSON (`edge_cards`).
 *
 * Two sizes: `compact` for the Preview (one row per lever, no chips), full for the Matchups tab. Colour is the
 * team's own through the page's `[data-matchup]` (`colorOf`). After the game a check marks each lever won.
 */
import type { EdgeSide, PathLever } from '../data/contract'
import { ordinal } from '../lib/rank'

const share = (rank: number, n: number) => Math.max(0.06, (n + 1 - rank) / n)

const ROLE_PLURAL: Record<EdgeSide['role'], string> = { underdog: 'Underdogs', favorite: 'Favorites', pick: 'Teams in close games' }

function roleLabel(s: EdgeSide): string {
  if (s.role === 'pick') return "pick'em"
  return `${s.role} ${s.role === 'underdog' ? '+' : '−'}${s.size}`
}

function RankBar({ team, noun, rank, n, color }: { team: string; noun: string; rank: number; n: number; color: string }) {
  return (
    <div className="flex items-center gap-2 text-[12px]">
      <span className="w-[9.5rem] shrink-0 truncate text-ink-2" title={`${team}'s ${noun}`}>
        {team}'s {noun}
      </span>
      <span className="relative h-2 flex-1 rounded" style={{ background: 'var(--band)' }}>
        <span className="absolute left-0 top-0 h-2 rounded" style={{ width: `${100 * share(rank, n)}%`, background: color }} />
      </span>
      <span className="tabular w-9 shrink-0 text-right font-semibold">{ordinal(rank)}</span>
    </div>
  )
}

function Lift({ base, did, who, color }: { base: number | null; did: number | null; who: string; color: string }) {
  if (base == null || did == null) return null
  const h = (p: number) => `${Math.max(4, (p / 100) * 52)}px`
  return (
    <div className="flex flex-col gap-1 text-[11px] text-ink-2" role="img" aria-label={`${who} won ${base}% of all games, and ${did}% when they won this battle`}>
      <span>{who}' win rate</span>
      <div className="flex items-end gap-3">
        <div className="flex flex-col items-center gap-0.5">
          <span className="tabular font-semibold text-ink">{base}%</span>
          <i className="block w-8 rounded-t-sm" style={{ height: h(base), background: 'var(--band-strong)' }} />
          <span>all games</span>
        </div>
        <div className="flex flex-col items-center gap-0.5">
          <span className="tabular font-semibold text-ink">{did}%</span>
          <i className="block w-8 rounded-t-sm" style={{ height: h(did), background: color }} />
          <span>won the battle</span>
        </div>
      </div>
    </div>
  )
}

const isCoin = (lv: PathLever) => lv.plausibility.startsWith('coin flip')
/** How well it repeats, in the hover text only (Austin, 2026-11-12: the win-rate bars carry the point). */
const plausibilityText = (lv: PathLever) => (isCoin(lv) ? 'More luck than skill: it barely repeats week to week.' : `${lv.plausibility[0].toUpperCase()}${lv.plausibility.slice(1)} from week to week.`)

function Mark({ met }: { met: boolean }) {
  return (
    <span role="img" aria-label={met ? 'won it' : "didn't"} data-met={met ? 'yes' : 'no'} className={`shrink-0 text-[12px] ${met ? 'text-ink' : 'text-ink-3'}`}>
      {met ? '✓ won it' : '– didn’t'}
    </span>
  )
}

function LeverCard({ lv, s, colorOf }: { lv: PathLever; s: EdgeSide; colorOf: (t: string) => string }) {
  return (
    <li data-testid={`lever-${lv.id}`} className="flex flex-col gap-2 rounded-lg border border-line p-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[14px] font-semibold" title={plausibilityText(lv)}>
          {lv.label}
        </span>
        {s.met && <Mark met={s.met.includes(lv.id)} />}
      </div>
      <RankBar team={s.team} noun={lv.dog_noun} rank={lv.dog_rank} n={lv.n_teams} color={colorOf(s.team)} />
      <RankBar team={s.opponent} noun={lv.fav_noun} rank={lv.fav_rank} n={lv.n_teams} color={colorOf(s.opponent)} />
      <Lift base={lv.base_rate_pct} did={lv.win_rate_pct} who={ROLE_PLURAL[s.role]} color={colorOf(s.team)} />
    </li>
  )
}

/** One lever as a row: label, the two units as thin bars with their ranks, and the win rates. */
function LeverRow({ lv, s, colorOf }: { lv: PathLever; s: EdgeSide; colorOf: (t: string) => string }) {
  return (
    <li data-testid={`lever-${lv.id}`} className="grid grid-cols-[minmax(0,1fr)_5.5rem_4.5rem] items-center gap-2 border-b border-line py-1.5 text-[12.5px]">
      <span className="min-w-0 truncate" title={plausibilityText(lv)}>
        {lv.label}
                {s.met && <span className="ml-1">{s.met.includes(lv.id) ? '✓' : ''}</span>}
      </span>
      <span className="flex flex-col gap-[2px]" title={`${s.team}'s ${lv.dog_noun} ${ordinal(lv.dog_rank)}; ${s.opponent}'s ${lv.fav_noun} ${ordinal(lv.fav_rank)}`}>
        <span className="block h-[5px] rounded-sm" style={{ width: `${100 * share(lv.dog_rank, lv.n_teams)}%`, background: colorOf(s.team) }} />
        <span className="block h-[5px] rounded-sm" style={{ width: `${100 * share(lv.fav_rank, lv.n_teams)}%`, background: colorOf(s.opponent) }} />
        <span className="tabular text-[10.5px] text-ink-3">
          {ordinal(lv.dog_rank)} vs {ordinal(lv.fav_rank)}
        </span>
      </span>
      <span className="tabular text-right" title={`${ROLE_PLURAL[s.role]} won ${lv.base_rate_pct}% of all games, ${lv.win_rate_pct}% when they won this battle`}>
        <span className="text-ink-3">{lv.base_rate_pct}%</span> → <b>{lv.win_rate_pct}%</b>
      </span>
    </li>
  )
}

const KIND: Record<'even' | 'favorite' | 'weak', (opp: string) => string> = {
  even: () => 'even',
  favorite: (opp) => `${opp}'s edge`,
  weak: () => 'neither strong',
}

export function EdgeCard({ side: s, colorOf, compact = false }: { side: EdgeSide; colorOf: (t: string) => string; compact?: boolean }) {
  const levers = s.levers ?? []
  return (
    <section data-testid={`edge-card-${s.team}`} data-role={s.role} className="min-w-0">
      <h3 className={`m-0 flex items-baseline gap-2 border-l-[3px] pl-2 font-semibold leading-tight ${compact ? 'text-[13.5px]' : 'text-[15px]'}`} style={{ borderColor: colorOf(s.team) }}>
        Where {s.team} has the edge <span className="tabular text-[12px] font-normal text-ink-3">{roleLabel(s)}</span>
      </h3>
      {!compact && (
        <p className="mb-3 mt-1 max-w-3xl text-[13px] text-ink-2">
          {s.base_rate_pct != null && <>{ROLE_PLURAL[s.role]} of this size won {s.base_rate_pct}% of games (2006–2025). </>}
          {levers.length > 0 ? `Where ${s.team}'s strong units meet weak ${s.opponent} ones, and how often teams like it that won that battle won the game:` : `No clear mismatch: none of ${s.team}'s strong units meets a weak ${s.opponent} unit.`}
        </p>
      )}
      {compact ? (
        levers.length > 0 ? (
          <ul className="m-0 mt-1 list-none p-0">
            {levers.map((lv) => (
              <LeverRow key={lv.id} lv={lv} s={s} colorOf={colorOf} />
            ))}
          </ul>
        ) : (
          <p className="m-0 mt-1 text-[12.5px] text-ink-2">No clear mismatch for {s.team}.</p>
        )
      ) : (
        levers.length > 0 && (
          <ul className="m-0 grid list-none grid-cols-1 gap-3 p-0 sm:grid-cols-2">
            {levers.map((lv) => (
              <LeverCard key={lv.id} lv={lv} s={s} colorOf={colorOf} />
            ))}
          </ul>
        )
      )}
      {!compact && (s.chips ?? []).length > 0 && (
        <>
          <h4 className="mb-1 mt-4 text-[12px] font-semibold text-ink-2">Not where {s.team}'s edge is</h4>
          <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
            {s.chips.map((c) => (
              <li key={c.id} data-testid={`chip-${c.id}`} data-kind={c.kind} title={c.text} className="rounded-full border border-dashed border-line px-2 py-0.5 text-[11.5px] text-ink-2">
                {c.label}: {KIND[c.kind](s.opponent)} ({ordinal(c.dog_rank)} vs {ordinal(c.fav_rank)})
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
