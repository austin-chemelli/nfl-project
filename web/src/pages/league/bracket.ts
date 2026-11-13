/**
 * The projected bracket (M26.4 follow-up, Austin 2026-11-12): one plausible playoff field and path
 * drawn from the simulated odds, not a forecast of its own.
 *
 * Seeds: the assignment of teams to seeds 1-7 that maximizes the summed P(team holds that seed),
 * solved exactly (DP over which seeds are filled), so a team that leads two seeds lands in one.
 * Games: the team more likely to reach the next round advances (the Super Bowl: more likely to win
 * it). Reseeding follows the NFL: the 1 seed meets the lowest seed left. The numbers on each team
 * are its chance to reach that round across every simulated season.
 */
import type { LeagueOddsTeam } from '../../data/contract'

export type OddsMap = Record<string, LeagueOddsTeam>
export type Seeded = { team: string; seed: number } // seed is 1-based
export type Game = { a: Seeded; b: Seeded; winner: Seeded }
export type ConfBracket = { seeds: Seeded[]; wildCard: Game[]; bye: Seeded[]; divisional: Game[]; conference: Game; champ: Seeded }

/** Teams in `teams` assigned to seeds 1..n, maximizing the summed seed probabilities. Ties keep the order of `teams`. */
export function projectSeeds(teams: string[], odds: OddsMap, n = 7): string[] {
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
        const v = (p[k] ?? 0) + best[i + 1][mask | (1 << k)]
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
