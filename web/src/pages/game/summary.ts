/**
 * The game page's summary strip (ADR 0017): five tiles, each one statement a reader would want
 * first, linking to the tab that explains it. Pure functions over the contract so both cases are
 * unit-tested.
 *
 * Before kickoff: the pick, how it sits against the market, what drives the pick, and the key
 * absence (or the biggest edge when no one is out). How the approaches split lives on their tab.
 * After the game: upset or not, how the approaches did, whether the play matched the result, which
 * way the swing plays went, and the biggest surprise against a team's season.
 */
import type { Efficiency, Game, Meta, RetroGame, TeamRetro } from '../../data/contract'
import { pct } from '../../lib/format'
import { groupOf, isContextOnly } from '../../lib/meta'
import { APPROACHES, HEADLINE, SHORT } from '../../lib/models'
import { injuryRank, sortInjuries } from './helpers'

export type TabId = 'retro' | 'preview' | 'approaches' | 'tendencies' | 'details' | 'news'

export type TileSpec = {
  id: string
  label: string
  value: string
  sub: string
  tab: TabId
  modelId?: string
  /** The team this tile is about, for its accent. */
  team?: string
}

const fav = (p: number, home: string, away: string) => (p >= 0.5 ? home : away)
const favPct = (p: number) => pct(p >= 0.5 ? p : 1 - p)
const one = (x: number) => Math.abs(x).toFixed(1)
/** Within 5 points of 50%: called a toss-up rather than an upset or a better side. */
const TOSS_UP = 0.05

/** Pure luck: the factors not marked partly skill (fumble recoveries, kicks, return plays). */
export const pureLuck = (t: TeamRetro) => Math.round(t.luck.filter((f) => !f.partly_skill).reduce((a, f) => a + f.swing_pts, 0) * 10) / 10

function winnerOf(g: Game): string | null {
  const m = g.result?.margin
  if (m == null || m === 0) return null
  return m > 0 ? g.home : g.away
}

export function summaryTiles(g: Game, meta: Meta, retro: RetroGame | null): TileSpec[] {
  if (g.result == null) return pregameTiles(g, meta)
  return retro != null ? finishedTiles(g, retro) : finishedNoRetroTiles(g, meta)
}

// ------------------------------------------------------------------------------------- shared

const marketP = (g: Game) => g.market?.p_home ?? g.models.market_baseline?.p_home ?? null

/** Upset or not, from the market's pregame view. */
function resultTile(g: Game, tab: TabId): TileSpec {
  const w = winnerOf(g)
  const mk = marketP(g)
  if (w == null) return { id: 'result', label: 'Result', value: 'Tie', sub: mk == null ? 'no market line' : `market had ${fav(mk, g.home, g.away)} ${favPct(mk)}`, tab }
  if (mk == null) return { id: 'result', label: 'Result', value: `${w} won`, sub: 'no market line', tab }
  const pW = w === g.home ? mk : 1 - mk
  if (Math.abs(pW - 0.5) < TOSS_UP) return { id: 'result', label: 'Result', value: 'Toss-up', sub: `${w} won; the market had it ${pct(pW)}`, tab }
  return pW < 0.5
    ? { id: 'result', label: 'Result', value: 'Upset', sub: `${w} won as a ${pct(pW)} underdog`, tab, team: w }
    : { id: 'result', label: 'Result', value: 'Favorite won', sub: `${w} was ${pct(pW)} in the market`, tab, team: w }
}

/** How many approaches picked the winner, from the game file's picks. */
function approachesRight(g: Game): { right: string[]; n: number } {
  const w = winnerOf(g)
  const ps = APPROACHES.filter((a) => g.models[a]?.p_home != null)
  const right = w == null ? [] : ps.filter((a) => fav(g.models[a].p_home, g.home, g.away) === w)
  return { right: right.map((a) => SHORT[a]), n: ps.length }
}

// ------------------------------------------------------------------------------------- pregame

function pregameTiles(g: Game, meta: Meta): TileSpec[] {
  const tiles: TileSpec[] = [pickTile(g), marketTile(g, meta.generated_at), factorTile(g, meta)]
  const absence = absenceTile(g)
  tiles.push(absence ?? edgeTile(g, meta) ?? { id: 'absence', label: 'Key absence', value: 'None listed', sub: g.injuries.length ? 'no one out or doubtful' : 'no injury report yet', tab: 'news' })
  return tiles
}

function pickTile(g: Game): TileSpec {
  const p = g.models[HEADLINE]?.p_home
  if (p == null) return { id: 'pick', label: 'The pick', value: '–', sub: 'not scored yet', tab: 'approaches' }
  return { id: 'pick', label: 'The pick', value: `${fav(p, g.home, g.away)} ${favPct(p)}`, sub: `the ${SHORT[HEADLINE]}'s line`, tab: 'approaches', modelId: HEADLINE, team: fav(p, g.home, g.away) }
}

/** The line's date when it is more than 3 days older than the site data (lines for later weeks lag). */
function lineAge(asOf: string | null | undefined, now: string): string {
  if (!asOf) return ''
  const days = (Date.parse(now) - Date.parse(asOf)) / 86_400_000
  if (!(days > 3)) return ''
  return ` · line from ${new Date(asOf).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'America/New_York' })}`
}

function marketTile(g: Game, now: string): TileSpec {
  const mk = marketP(g)
  const p = g.models[HEADLINE]?.p_home
  const line = g.market?.spread_home
  const mkText = mk == null
    ? 'no market line yet'
    : `market ${fav(mk, g.home, g.away)} ${favPct(mk)}${line != null && Math.abs(line) >= 0.25 ? `, ${line > 0 ? g.home : g.away} −${Math.abs(line)}` : ''}${lineAge(g.market?.as_of, now)}`
  if (mk == null || p == null) return { id: 'market', label: 'vs the market', value: '–', sub: mkText, tab: 'approaches' }
  const d = Math.round(100 * (p - mk))
  if (fav(p, g.home, g.away) !== fav(mk, g.home, g.away)) return { id: 'market', label: 'vs the market', value: 'Other side', sub: mkText, tab: 'approaches' }
  if (Math.abs(d) < 3) return { id: 'market', label: 'vs the market', value: 'In line', sub: mkText, tab: 'approaches' }
  return { id: 'market', label: 'vs the market', value: `${Math.abs(d)} pts more on ${d > 0 ? g.home : g.away}`, sub: mkText, tab: 'approaches' }
}

/** The group (or home field) that moves the headline line most. */
function factorTile(g: Game, meta: Meta): TileSpec {
  const c = g.contributions[HEADLINE]
  if (!c) return { id: 'factor', label: 'Biggest factor', value: '–', sub: 'no breakdown', tab: 'preview' }
  const items = [
    { name: 'Home field', pp: c.home_field_pp ?? 0 },
    ...Object.entries(c.groups).map(([id, x]) => ({ name: groupOf(meta, id)?.name ?? id, pp: x.pp ?? 0 })),
  ]
  const top = items.reduce((a, b) => (Math.abs(b.pp) > Math.abs(a.pp) ? b : a))
  return { id: 'factor', label: 'Biggest factor', value: top.name, sub: `${one(top.pp)} pts toward ${top.pp >= 0 ? g.home : g.away}`, tab: 'preview', team: top.pp >= 0 ? g.home : g.away }
}

/** Position weight for "key": the injury file has no importance field, so the position stands in for it. */
const POS_RANK: [RegExp, number][] = [[/^QB$/, 0], [/^(WR|RB|TE|FB)$/, 1], [/^(T|G|C|OT|OG|OL|LT|RT)$/, 2], [/^(K|P|LS)$/, 4]]
const posRank = (pos: string | null) => POS_RANK.find(([re]) => re.test(pos ?? ''))?.[1] ?? 3
/** Long-term lists (IR, PUP, NFI) were already missing for weeks; they're not this week's news. */
const LONG_TERM = /\b(ir|pup|nfi)\b|reserve/i

/** This week's absences: out before doubtful, then by position (QB, skill, line, defense, specialists). */
function absenceTile(g: Game): TileSpec | null {
  const out = sortInjuries(g.injuries.filter((i) => injuryRank(i.status) <= 1 && !LONG_TERM.test(i.status))).sort(
    (a, b) => posRank(a.pos) - posRank(b.pos) || injuryRank(a.status) - injuryRank(b.status),
  )
  if (out.length === 0) return null
  const i = out[0]
  return { id: 'absence', label: 'Key absence', value: i.player, sub: `${i.team}${i.pos ? ` ${i.pos}` : ''}, ${i.status.toLowerCase()}${out.length > 1 ? ` · +${out.length - 1} more` : ''}`, tab: 'news', team: i.team }
}

function edgeTile(g: Game, meta: Meta): TileSpec | null {
  const edges = Object.entries(g.edges)
    .filter(([id, e]) => e.favors && e.strength_pct != null && !isContextOnly(meta, id))
    .sort(([, a], [, b]) => (b.strength_pct ?? 0) - (a.strength_pct ?? 0))
  if (edges.length === 0) return null
  const [id, e] = edges[0]
  return { id: 'edge', label: 'Biggest edge', value: `${e.favors} ${groupOf(meta, id)?.name ?? id}`, sub: `bigger than ${Math.round(e.strength_pct ?? 0)}% of matchups`, tab: 'preview', team: e.favors ?? undefined }
}

// ------------------------------------------------------------------------------------ finished

function finishedTiles(g: Game, r: RetroGame): TileSpec[] {
  const approaches = r.predictions.filter((p) => p.kind === 'approach')
  const right = approaches.filter((p) => p.right)
  const best = r.predictions.find((p) => p.best)
  const pl = r.played_like
  const plP = pl.favored === r.home ? pl.p_home : 1 - pl.p_home
  const tie = winnerOf(g) == null
  const tiles: TileSpec[] = [
    resultTile(g, 'retro'),
    {
      id: 'right', label: 'Approaches right', tab: 'retro',
      value: tie || approaches.length === 0 ? '–' : `${right.length} of ${approaches.length}`,
      sub: [tie ? 'a tie' : null, best ? `best read: ${best.label.replace(/^The /, '')}` : 'no approach forecasts'].filter(Boolean).join(' · '),
      modelId: best?.model_id,
    },
    plP - 0.5 < TOSS_UP
      ? { id: 'played', label: 'Played like', tab: 'retro', value: 'About even', sub: `${pl.favored} ${pct(plP)} by efficiency` }
      : {
          id: 'played', label: 'Played like', tab: 'retro', team: pl.favored,
          value: `${pl.favored} ${pct(plP)}`,
          sub: pl.matches_result == null ? 'the better side; a tie' : pl.matches_result ? 'the better side, and won' : 'the better side, but lost',
        },
    swingTile(r),
  ]
  const s = surpriseTile(r)
  if (s) tiles.push(s)
  return tiles
}

/** Which way the swing plays went (net), with the pure-luck part. */
function swingTile(r: RetroGame): TileSpec {
  const net = r.teams.home.luck_net - r.teams.away.luck_net
  const pure = pureLuck(r.teams.home) - pureLuck(r.teams.away)
  const side = (x: number) => (x >= 0 ? r.home : r.away)
  return {
    id: 'swing', label: 'Swing plays', tab: 'retro', team: Math.abs(net) < 1 ? undefined : side(net),
    value: Math.abs(net) < 1 ? 'Even' : `${side(net)} +${one(net)} pts`,
    sub: Math.abs(pure) < 1 ? 'pure luck about even' : `pure luck ${side(pure)} +${one(pure)}`,
  }
}

const SURPRISE: Record<string, string> = {
  off_epa_play: 'offense', off_epa_dropback: 'passing', off_epa_rush: 'running',
  def_epa_play: 'defense', def_epa_dropback: 'pass defense', def_epa_rush: 'run defense',
}

/**
 * The unit that played furthest from its season level, measured against the league's spread of
 * teams (the p10–p90 band) so a metric with a wide range doesn't win by default.
 */
function surpriseTile(r: RetroGame): TileSpec | null {
  let top: { team: string; e: Efficiency; z: number } | null = null
  for (const t of [r.teams.away, r.teams.home]) {
    for (const e of t.efficiency) {
      if (!(e.metric in SURPRISE) || e.game == null || e.season == null) continue
      const width = e.league_lo != null && e.league_hi != null ? e.league_hi - e.league_lo : null
      if (!width) continue
      const z = (e.game - e.season) / width
      if (!top || Math.abs(z) > Math.abs(top.z)) top = { team: t.team, e, z }
    }
  }
  if (!top) return null
  const d = top.e.game! - top.e.season!
  const better = (d > 0) === top.e.higher_is_better
  const per = top.e.metric.includes('dropback') ? 'a dropback' : top.e.metric.includes('rush') ? 'a rush' : 'a play'
  return {
    id: 'surprise', label: 'Biggest surprise', tab: 'retro', team: top.team,
    value: `${top.team} ${SURPRISE[top.e.metric]}`,
    sub: `${better ? 'better' : 'worse'} than its season by ${Math.abs(d).toFixed(2)} EPA ${per}`,
  }
}

/** A final game whose retro isn't built yet: what can be said from the game file. */
function finishedNoRetroTiles(g: Game, meta: Meta): TileSpec[] {
  const { right, n } = approachesRight(g)
  const tie = winnerOf(g) == null
  return [
    resultTile(g, 'approaches'),
    tie || n === 0
      ? { id: 'right', label: 'Approaches right', value: '–', sub: tie ? 'a tie' : 'no approach forecasts', tab: 'approaches' }
      : { id: 'right', label: 'Approaches right', value: `${right.length} of ${n}`, sub: right.length ? right.join(', ') : 'none picked the winner', tab: 'approaches' },
    pickTile(g),
    factorTile(g, meta),
    { id: 'pending', label: 'Retrospective', value: 'Coming', sub: 'built the morning after a game', tab: 'approaches' },
  ]
}
