/**
 * The projected bracket (M26.4 follow-up, Austin 2026-11-12): one plausible playoff field and path
 * drawn from the simulated odds, not a forecast of its own.
 *
 * Field (bracket fix, 2026-11-15): valid by construction and in line with the playoff odds. Each division
 * goes to its most likely winner (P(win division)); the wild cards to the other teams most likely to make
 * the playoffs. Only then are seeds ordered, within each group (1-4 the division winners, 5-7 the wild
 * cards), by the assignment that maximizes the summed P(team holds that seed), so a team that leads two
 * seeds lands in one. Seeding the whole conference that way put two NFC East teams in seeds 3-4, and CLE
 * (32%) in as the 7 seed over KC (84%), whose chances sat in seeds other teams were given.
 * Games: the team more likely to reach the next round advances (the Super Bowl: more likely to win
 * it). Reseeding follows the NFL: the 1 seed meets the lowest seed left. The numbers on each team
 * are its chance to reach that round across every simulated season.
 */
import type { LeagueOddsTeam } from '../../data/contract'

export type OddsMap = Record<string, LeagueOddsTeam>
export type Seeded = { team: string; seed: number } // seed is 1-based
export type Game = { a: Seeded; b: Seeded; winner: Seeded }
export type ConfBracket = { seeds: Seeded[]; wildCard: Game[]; bye: Seeded[]; divisional: Game[]; conference: Game; champ: Seeded }

/**
 * Teams in `teams` assigned to seeds offset+1..offset+n, maximizing the summed seed probabilities.
 * Ties keep the order of `teams`.
 */
export function projectSeeds(teams: string[], odds: OddsMap, n = 7, offset = 0): string[] {
  const full = (1 << n) - 1
  const m = teams.length
  // best[i][mask]: best sum using teams i.. with `mask` seeds already taken; -Infinity when the rest can't be filled
  const best: number[][] = Array.from({ length: m + 1 }, () => new Array(full + 1).fill(-Infinity))
  const choice: number[][] = Array.from({ length: m + 1 }, () => new Array(full + 1).fill(-1))
  best[m][full] = 0
  for (let i = m - 1; i >= 0; i--) {
    const p = odds[teams[i]]?.seed ?? []
    for (let mask = 0; mask <= full; mask++) {
      let b = best[i + 1][mask] // this team gets no seed
      let c = -1
      for (let k = 0; k < n; k++) {
        if (mask & (1 << k)) continue
        const v = (p[offset + k] ?? 0) + best[i + 1][mask | (1 << k)]
        if (v > b + 1e-12) {
          b = v
          c = k
        }
      }
      best[i][mask] = b
      choice[i][mask] = c
    }
  }
  const out: string[] = new Array(n)
  let mask = 0
  for (let i = 0; i < m; i++) {
    const k = choice[i][mask]
    if (k >= 0) {
      out[k] = teams[i]
      mask |= 1 << k
    }
  }
  return out
}

export type Field = {
  seeds: string[]
  /** division name -> its projected winner (seeds 1..divisions) */
  divWinner: Record<string, string>
  /** teams left out, most likely to make the playoffs first */
  out: string[]
}

/**
 * The projected field of one conference: one division winner per division in the top seeds, the wild
 * cards from the rest by playoff chance, `nSeeds` in all. Ties go to the higher playoff chance, then the
 * order of `teams`.
 */
export function projectField(teams: { team: string; div: string }[], odds: OddsMap, nSeeds = 7): Field {
  const po = (t: string) => odds[t]?.playoffs ?? 0
  const byPlayoffs = teams.map((t, i) => ({ ...t, i })).sort((a, b) => po(b.team) - po(a.team) || a.i - b.i)
  const divWinner: Record<string, string> = {}
  const pDiv = (t: string) => odds[t]?.division ?? 0
  for (const t of byPlayoffs) {
    const cur = divWinner[t.div]
    if (cur == null || pDiv(t.team) > pDiv(cur) + 1e-12) divWinner[t.div] = t.team
  }
  const winners = byPlayoffs.filter((t) => divWinner[t.div] === t.team).map((t) => t.team)
  const nWild = Math.max(0, nSeeds - winners.length)
  const rest = byPlayoffs.filter((t) => divWinner[t.div] !== t.team).map((t) => t.team)
  const wild = rest.slice(0, nWild)
  return {
    seeds: [...projectSeeds(winners, odds, winners.length), ...projectSeeds(wild, odds, wild.length, winners.length)],
    divWinner,
    out: rest.slice(nWild),
  }
}

const reach = (odds: OddsMap, t: string, round: 'div' | 'conf' | 'sb' | 'champ') => odds[t]?.rounds[round] ?? 0

function play(a: Seeded, b: Seeded, odds: OddsMap, round: 'div' | 'conf' | 'sb' | 'champ'): Game {
  const [hi, lo] = a.seed < b.seed ? [a, b] : [b, a]
  const winner = reach(odds, lo.team, round) > reach(odds, hi.team, round) ? lo : hi
  return { a: hi, b: lo, winner }
}

/** One conference's projected bracket from its seeds (7 seeds: one bye; 6 seeds: two). */
export function projectConference(seedTeams: string[], odds: OddsMap): ConfBracket {
  const seeds = seedTeams.map((team, i) => ({ team, seed: i + 1 }))
  const n = seeds.length
  const nBye = 8 - n
  const bye = seeds.slice(0, nBye)
  const wildCard: Game[] = []
  for (let s = nBye; s < 4; s++) wildCard.push(play(seeds[s], seeds[n - 1 - (s - nBye)], odds, 'div'))
  const alive = [...bye, ...wildCard.map((g) => g.winner)].sort((x, y) => x.seed - y.seed)
  const divisional = [play(alive[0], alive[3], odds, 'conf'), play(alive[1], alive[2], odds, 'conf')]
  const conference = play(divisional[0].winner, divisional[1].winner, odds, 'sb')
  return { seeds, wildCard, bye, divisional, conference, champ: conference.winner }
}

/** The Super Bowl between the two conference champions (neutral site): the more likely champion wins. */
export function superBowl(afc: Seeded, nfc: Seeded, odds: OddsMap): { afc: Seeded; nfc: Seeded; winner: Seeded } {
  const winner = reach(odds, nfc.team, 'champ') > reach(odds, afc.team, 'champ') ? nfc : afc
  return { afc, nfc, winner }
}

export type Rec = { w: number; l: number; t: number }
export type RecordView = { now: Rec; added: { w: number; l: number }; proj: Rec; projWas?: Rec }

/** Final record from the expected wins (ties count half in the engine): wins rounded, the rest losses. */
export function projected(st: { w: number; l: number; t: number; left: number }, winsMean: number): Rec {
  const total = st.w + st.l + st.t + st.left
  const w = Math.max(st.w, Math.min(total - st.t - st.l, Math.round(winsMean - st.t / 2)))
  return { w, l: total - st.t - w, t: st.t }
}

/** A team's record now plus the games decided in a scenario, and its projected final record (and the one before the decisions). */
export function recordView(
  st: { team: string; w: number; l: number; t: number; left: number },
  decided: { home: string; away: string; winner: 'home' | 'away' }[],
  winsMean: number,
  wasWinsMean?: number,
): RecordView {
  let w = 0
  let l = 0
  for (const g of decided) {
    if (g.home !== st.team && g.away !== st.team) continue
    if ((g.winner === 'home') === (g.home === st.team)) w++
    else l++
  }
  return {
    now: { w: st.w + w, l: st.l + l, t: st.t },
    added: { w, l },
    proj: projected(st, winsMean),
    projWas: wasWinsMean == null ? undefined : projected(st, wasWinsMean),
  }
}
