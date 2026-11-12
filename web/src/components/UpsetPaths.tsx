/**
 * Where the underdog has the edge (ADR 0028, M25; redesign 2026-11-12): up to four levers, each a condition
 * where the dog's unit ranks well and the favourite's matching unit ranks poorly, drawn as two rank bars and
 * the history: all dogs of this size against dogs who met the condition. Conditions that aren't the dog's
 * edge are grey chips. Context, never a forecast: no probability for the upset appears here, and every number
 * is read from the JSON. Finished games add a check on each lever the dog met. Colour: the dog is
 * `--team-away`, the favourite `--team-home`, through `[data-matchup]`.
 */
import type { PathChip, PathLever, PathsOutcome, UpsetPaths as Paths } from '../data/contract'
import { ordinal } from '../lib/rank'
import { matchupVars } from '../lib/teamColors'

const sizeLabel = (n: number) => (n > 0 ? `+${n}` : String(n))
const share = (rank: number, n: number) => Math.max(0.06, (n + 1 - rank) / n)
const DOG = 'var(--team-away)'
const FAV = 'var(--team-home)'

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

function Lift({ base, did }: { base: number | null; did: number | null }) {
  if (base == null || did == null) return null
  const h = (p: number) => `${Math.max(4, (p / 100) * 52)}px`
  return (
    <div className="flex items-end gap-3 text-[11px] text-ink-2" aria-label={`all dogs of this size won ${base}%, dogs who did this won ${did}%`} role="img">
      <div className="flex flex-col items-center gap-0.5">
        <span className="tabular font-semibold text-ink">{base}%</span>
        <i className="block w-8 rounded-t-sm" style={{ height: h(base), background: 'var(--band-strong)' }} />
        <span>all dogs</span>
      </div>
      <div className="flex flex-col items-center gap-0.5">
        <span className="tabular font-semibold text-ink">{did}%</span>
        <i className="block w-8 rounded-t-sm" style={{ height: h(did), background: DOG }} />
        <span>did this</span>
      </div>
    </div>
  )
}

function LeverCard({ lv, dog, fav, met }: { lv: PathLever; dog: string; fav: string; met: boolean | undefined }) {
  const coin = lv.plausibility.startsWith('coin flip')
  return (
    <li data-testid={`lever-${lv.id}`} className="flex flex-col gap-2 rounded-lg border border-line p-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[14px] font-semibold">{lv.label}</span>
        {met !== undefined && (
          <span role="img" aria-label={met ? 'met' : 'not met'} data-met={met ? 'yes' : 'no'} className={met ? 'text-ink' : 'text-ink-3'}>
            {met ? '✓ did it' : '– didn’t'}
          </span>
        )}
      </div>
      <RankBar team={dog} noun={lv.dog_noun} rank={lv.dog_rank} n={lv.n_teams} color={DOG} />
      <RankBar team={fav} noun={lv.fav_noun} rank={lv.fav_rank} n={lv.n_teams} color={FAV} />
      <Lift base={lv.base_rate_pct} did={lv.win_rate_pct} />
      <span
        data-testid="lever-plausibility"
        className="self-start rounded-full border px-1.5 text-[10.5px]"
        style={{ borderColor: coin ? 'var(--warning)' : 'var(--border)', color: coin ? 'var(--warning)' : 'var(--text-muted)' }}
      >
        {coin ? 'more luck than skill: it barely repeats week to week' : lv.plausibility}
      </span>
    </li>
  )
}

const KIND: Record<PathChip['kind'], (fav: string) => string> = {
  even: () => 'even',
  favorite: (fav) => `${fav}'s edge`,
  weak: () => 'neither strong',
}

export function UpsetPaths({ paths, outcome }: { paths: Paths | null; outcome?: PathsOutcome | null }) {
  if (!paths) return null
  const met = new Map((outcome?.conditions ?? []).map((c) => [c.id, c.met]))
  const levers = paths.levers ?? []
  const chips = paths.chips ?? []
  return (
    <section className="mt-8" data-testid="upset-paths" data-matchup style={matchupVars(paths.dog, paths.favorite)}>
      <h3 className="m-0 border-l-[3px] pl-2 text-[15px] font-semibold leading-tight" style={{ borderColor: DOG }}>
        Where {paths.dog} has the edge <span className="tabular font-normal text-ink-2">{sizeLabel(paths.size)}</span>
      </h3>
      <p className="mb-3 mt-1 max-w-3xl text-[13px] text-ink-2">
        {paths.base_rate_pct != null && <>Underdogs of this size won {paths.base_rate_pct}% of games (2006–2025). </>}
        {levers.length > 0
          ? `Where ${paths.dog}'s strong units meet weak ${paths.favorite} ones, and how often dogs who won that battle won the game:`
          : paths.sentence}
      </p>
      {levers.length > 0 && (
        <ul className="m-0 grid list-none grid-cols-1 gap-3 p-0 sm:grid-cols-2">
          {levers.map((lv) => (
            <LeverCard key={lv.id} lv={lv} dog={paths.dog} fav={paths.favorite} met={outcome ? met.get(lv.id) : undefined} />
          ))}
        </ul>
      )}
      {chips.length > 0 && (
        <>
          <h4 className="mb-1 mt-4 text-[12px] font-semibold text-ink-2">Not where {paths.dog}'s edge is</h4>
          <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
            {chips.map((c) => (
              <li
                key={c.id}
                data-testid={`chip-${c.id}`}
                data-kind={c.kind}
                title={c.text}
                className="rounded-full border border-dashed border-line px-2 py-0.5 text-[11.5px] text-ink-2"
              >
                {c.label}: {KIND[c.kind](paths.favorite)} ({ordinal(c.dog_rank)} vs {ordinal(c.fav_rank)})
              </li>
            ))}
          </ul>
        </>
      )}
      {outcome && <p className="mb-0 mt-3 max-w-3xl text-[13px] text-ink" data-testid="paths-outcome">{outcome.sentence}</p>}
    </section>
  )
}
