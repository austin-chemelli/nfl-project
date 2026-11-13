/**
 * Season Monte Carlo for the playoff what-if: a copy of src/nfl/league/simulate.py (M26.3, ADR 0029),
 * without leverage. Each run draws a team-strength shock, plays the remaining games (decided games
 * take the visitor's winner), seeds each conference by the tiebreakers and plays the bracket.
 *
 * Draws come per run in a fixed amount and order (32 shocks, one uniform per game, 13 for the bracket)
 * whether a game is decided or not, so two scenarios on the same seed share their random numbers:
 * the difference between them is the decisions, not noise. Coin flips use a separate stream.
 */
import { CONFS, TEAMS, type Conf } from './divisions'
import { Results, type GameResult } from './standings'
import { seedConference, type Rng } from './tiebreak'

export const ROUNDS = ['div', 'conf', 'sb', 'champ'] as const
export type Round = (typeof ROUNDS)[number]
const N_SEEDS = 7
const BRACKET_DRAWS = 13

export type SimGame = { id: string; home: string; away: string; p: number }
export type Winner = 'home' | 'away'

export type SimInput = {
  played: GameResult[]
  games: SimGame[]
  /** Logit ratings that price playoff games; a missing team counts 0. */
  ratings: Record<string, number>
  homeAdv: number
  sigma: number
  nSeeds?: 6 | 7
}

export type TeamOdds = {
  playoffs: number
  division: number
  bye: number
  seed: number[]
  rounds: Record<Round, number>
  winsMean: number
  winsLo: number
  winsHi: number
}

/** One run's random numbers, in the Python's layout (tests replay the Python's draws). */
export type RunDraws = { delta: ArrayLike<number>; uGames: ArrayLike<number>; uBracket: ArrayLike<number> }

export type SimOptions = {
  nRuns: number
  seed?: number
  /** game id -> the visitor's winner */
  decided?: ReadonlyMap<string, Winner>
  /** Tests: the draws of run `i` instead of the generator's. */
  draws?: (run: number) => RunDraws
  onRun?: (run: number, seeds: Record<Conf, string[]>, champ: string) => void
}

/** mulberry32: a small, fast seeded generator, uniform in [0, 1). */
export function mulberry32(seed: number): Rng {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const sigmoid = (x: number) => 1 / (1 + Math.exp(-x))

/** numpy's default (linear) percentile of an unsorted array. */
export function percentile(xs: Float64Array, q: number): number {
  const s = Float64Array.from(xs).sort()
  const pos = ((s.length - 1) * q) / 100
  const lo = Math.floor(pos)
  const hi = Math.min(lo + 1, s.length - 1)
  return s[lo] + (s[hi] - s[lo]) * (pos - lo)
}

export function simulateSeason(input: SimInput, opts: SimOptions): Record<string, TeamOdds> {
  const nSeeds = input.nSeeds ?? N_SEEDS
  const { nRuns } = opts
  const nt = TEAMS.length
  const ix = new Map(TEAMS.map((t, i) => [t, i]))
  const games = input.games
  const ng = games.length
  const hi = games.map((g) => ix.get(g.home)!)
  const ai = games.map((g) => ix.get(g.away)!)
  const logit = games.map((g) => Math.log(g.p / (1 - g.p)))
  const forced = games.map((g) => opts.decided?.get(g.id) ?? null)
  const rating = TEAMS.map((t) => input.ratings[t] ?? 0)
  const base = new Results(input.played)

  const baseWins = new Float64Array(nt)
  for (const r of input.played) {
    baseWins[ix.get(r.home)!] += r.outcome
    baseWins[ix.get(r.away)!] += 1 - r.outcome
  }

  const seedN = TEAMS.map(() => new Float64Array(N_SEEDS))
  const roundN: Record<Round, Float64Array> = { div: new Float64Array(nt), conf: new Float64Array(nt), sb: new Float64Array(nt), champ: new Float64Array(nt) }
  const winsByTeam = TEAMS.map(() => new Float64Array(nRuns))

  const uni = mulberry32(opts.seed ?? 1)
  const coinRng = mulberry32(((opts.seed ?? 1) ^ 0x9e3779b9) >>> 0)
  const delta = new Float64Array(nt)
  const uGames = new Float64Array(ng)
  const uBracket = new Float64Array(BRACKET_DRAWS)
  const normal = () => {
    // Box-Muller; 1 - u keeps the log finite
    const u = 1 - uni()
    const v = uni()
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v)
  }

  const simGames: GameResult[] = new Array(ng)
  for (let run = 0; run < nRuns; run++) {
    let d: ArrayLike<number>, ug: ArrayLike<number>, ub: ArrayLike<number>
    if (opts.draws) {
      const x = opts.draws(run)
      d = x.delta
      ug = x.uGames
      ub = x.uBracket
    } else {
      for (let i = 0; i < nt; i++) delta[i] = input.sigma * normal()
      for (let g = 0; g < ng; g++) uGames[g] = uni()
      for (let k = 0; k < BRACKET_DRAWS; k++) uBracket[k] = uni()
      d = delta
      ug = uGames
      ub = uBracket
    }

    const wins = Float64Array.from(baseWins)
    for (let g = 0; g < ng; g++) {
      const f = forced[g]
      const homeWin = f ? f === 'home' : ug[g] < sigmoid(logit[g] + d[hi[g]] - d[ai[g]])
      simGames[g] = { home: games[g].home, away: games[g].away, outcome: homeWin ? 1 : 0 }
      wins[homeWin ? hi[g] : ai[g]] += 1
    }
    for (let i = 0; i < nt; i++) winsByTeam[i][run] = wins[i]

    const results = base.extended(simGames)
    const winProb = (h: number, a: number, neutral: boolean) => sigmoid(rating[h] - rating[a] + (neutral ? 0 : input.homeAdv) + d[h] - d[a])
    let k = 0
    const champs = {} as Record<Conf, number>
    const seeded = {} as Record<Conf, string[]>
    for (const conf of CONFS) {
      seeded[conf] = seedConference(results, conf, coinRng, nSeeds)
      const seeds = seeded[conf].map((t) => ix.get(t)!)
      seeds.forEach((t, s) => (seedN[t][s] += 1))
      // a lower position hosts; one bracket draw per game
      const play = (a: number, b: number) => {
        const pA = winProb(seeds[a], seeds[b], false)
        k += 1
        return ub[k - 1] < pA ? a : b
      }
      const byes = 8 - nSeeds
      const wc: number[] = []
      for (let b = byes; b < 4; b++) wc.push(play(b, nSeeds - 1 - (b - byes)))
      let alive = [...Array.from({ length: byes }, (_, i) => i), ...wc].sort((x, y) => x - y)
      for (const s of alive) roundN.div[seeds[s]] += 1
      alive = [play(alive[0], alive[3]), play(alive[1], alive[2])].sort((x, y) => x - y)
      for (const s of alive) roundN.conf[seeds[s]] += 1
      champs[conf] = seeds[play(alive[0], alive[1])]
    }
    const [a, n] = [champs.AFC, champs.NFC]
    roundN.sb[a] += 1
    roundN.sb[n] += 1
    const champ = ub[k] < winProb(a, n, true) ? a : n // the AFC is the nominal home
    roundN.champ[champ] += 1
    opts.onRun?.(run, seeded, TEAMS[champ])
  }

  const out: Record<string, TeamOdds> = {}
  TEAMS.forEach((t, i) => {
    const s = seedN[i]
    const w = winsByTeam[i]
    let sum = 0
    for (const x of w) sum += x
    out[t] = {
      playoffs: s.reduce((x, y) => x + y, 0) / nRuns,
      division: (s[0] + s[1] + s[2] + s[3]) / nRuns,
      bye: s[0] / nRuns,
      seed: Array.from(s, (x) => x / nRuns),
      rounds: { div: roundN.div[i] / nRuns, conf: roundN.conf[i] / nRuns, sb: roundN.sb[i] / nRuns, champ: roundN.champ[i] / nRuns },
      winsMean: sum / nRuns,
      winsLo: percentile(w, 10),
      winsHi: percentile(w, 90),
    }
  })
  return out
}
