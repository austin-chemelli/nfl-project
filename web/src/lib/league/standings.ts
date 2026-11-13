/**
 * Standings measures behind the NFL tiebreakers: a copy of src/nfl/league/standings.py (M26.3).
 * Arithmetic follows the Python operation for operation, so equal records give equal floats and
 * the tiebreak steps compare exactly as there. Parity: web/src/test/fixtures/league_parity.
 */
import { CONFERENCE_SET, DIVISION_SET, DIVISIONS } from './divisions'

/** [wins, ties, games]; losses = games - wins - ties */
type WTN = [number, number, number]

export type GameResult = { home: string; away: string; outcome: number; homeScore?: number | null; awayScore?: number | null }

export function fromScores(home: string, away: string, hs: number, as: number): GameResult {
  return { home, away, outcome: hs > as ? 1 : hs < as ? 0 : 0.5, homeScore: hs, awayScore: as }
}

const ZERO: WTN = [0, 0, 0]

export class Results {
  tot: Map<string, WTN> = new Map()
  opp: Map<string, Map<string, WTN>> = new Map()
  pf: Map<string, number> = new Map()
  pa: Map<string, number> = new Map()
  net: Map<string, Map<string, number>> = new Map()
  scored = true
  private ownPts = true
  private cache = new Map<string, unknown>()

  constructor(games: Iterable<GameResult> = []) {
    this.add(games)
  }

  /** A new Results: this one's games plus `games`; this one is untouched. */
  extended(games: Iterable<GameResult>): Results {
    const n = Object.create(Results.prototype) as Results
    n.tot = new Map(this.tot)
    n.opp = new Map()
    for (const [t, d] of this.opp) n.opp.set(t, new Map(d))
    n.pf = this.pf
    n.pa = this.pa
    n.net = this.net
    n.ownPts = false
    n.scored = this.scored
    n.cache = new Map()
    n.add(games)
    return n
  }

  private add(games: Iterable<GameResult>) {
    for (const g of games) {
      const { home: h, away: a, outcome: o } = g
      let hw = 0, ht = 0, aw = 0, at = 0
      if (o === 1) hw = 1
      else if (o === 0) aw = 1
      else ht = at = 1
      const x = this.tot.get(h) ?? ZERO
      this.tot.set(h, [x[0] + hw, x[1] + ht, x[2] + 1])
      const y = this.tot.get(a) ?? ZERO
      this.tot.set(a, [y[0] + aw, y[1] + at, y[2] + 1])
      let d = this.opp.get(h)
      if (!d) this.opp.set(h, (d = new Map()))
      const p = d.get(a) ?? ZERO
      d.set(a, [p[0] + hw, p[1] + ht, p[2] + 1])
      let e = this.opp.get(a)
      if (!e) this.opp.set(a, (e = new Map()))
      const q = e.get(h) ?? ZERO
      e.set(h, [q[0] + aw, q[1] + at, q[2] + 1])
      if (g.homeScore == null || g.awayScore == null) this.scored = false
      else this.addPoints(h, a, g.homeScore, g.awayScore)
    }
  }

  private addPoints(h: string, a: string, hs: number, as: number) {
    if (!this.ownPts) {
      this.pf = new Map(this.pf)
      this.pa = new Map(this.pa)
      const net = new Map<string, Map<string, number>>()
      for (const [t, d] of this.net) net.set(t, new Map(d))
      this.net = net
      this.ownPts = true
    }
    const inc = (m: Map<string, number>, k: string, v: number) => m.set(k, (m.get(k) ?? 0) + v)
    inc(this.pf, h, hs)
    inc(this.pa, h, as)
    inc(this.pf, a, as)
    inc(this.pa, a, hs)
    if (!this.net.has(h)) this.net.set(h, new Map())
    if (!this.net.has(a)) this.net.set(a, new Map())
    inc(this.net.get(h)!, a, hs - as)
    inc(this.net.get(a)!, h, as - hs)
  }

  get teams(): string[] {
    return [...this.tot.keys()]
  }

  /** [wins, losses, ties] over every game. */
  record(team: string): [number, number, number] {
    const [w, t, n] = this.tot.get(team) ?? ZERO
    return [w, n - w - t, t]
  }

  /** Win percentage, a tie as half a win; 0 with no games. */
  pct(team: string): number {
    const [w, t, n] = this.tot.get(team) ?? ZERO
    return n ? (w + t / 2) / n : 0
  }

  recordVs(team: string, opps: Iterable<string>): [number, number, number] {
    const od = this.opp.get(team)
    let w = 0, t = 0, n = 0
    if (od) {
      for (const o of opps) {
        const x = od.get(o)
        if (x) {
          w += x[0]
          t += x[1]
          n += x[2]
        }
      }
    }
    return [w, n - w - t, t]
  }

  /** Win percentage against `opps`; null if the team played none of them. */
  pctVs(team: string, opps: Iterable<string>): number | null {
    const [w, l, t] = this.recordVs(team, opps)
    const n = w + l + t
    return n ? (w + t / 2) / n : null
  }

  gamesVs(team: string, opps: Iterable<string>): number {
    const [w, l, t] = this.recordVs(team, opps)
    return w + l + t
  }

  divisionRecord(team: string): [number, number, number] {
    return DIVISION_SET[team] ? this.recordVs(team, without(DIVISION_SET[team], [team])) : [0, 0, 0]
  }

  conferenceRecord(team: string): [number, number, number] {
    const d = DIVISIONS[team]
    return d ? this.recordVs(team, without(CONFERENCE_SET[d[0]], [team])) : [0, 0, 0]
  }

  /** Opponents every club in `teams` played, not counting the clubs themselves. */
  commonOpponents(teams: string[]): Set<string> {
    if (teams.length === 0) return new Set()
    const sets = teams.map((t) => new Set(this.opp.get(t)?.keys() ?? []))
    const out = new Set<string>()
    for (const o of sets[0]) if (sets.every((s) => s.has(o)) && !teams.includes(o)) out.add(o)
    return out
  }

  private oppPctSum(weights: [string, number][]): number {
    let num = 0, den = 0
    for (const [o, m] of weights) {
      const [w, t, n] = this.tot.get(o) ?? ZERO
      num += m * (2 * w + t)
      den += m * 2 * n
    }
    return den ? num / den : 0
  }

  /** Combined win percentage of the opponents this club beat (once per win). */
  sov(team: string): number {
    const k = `sov|${team}`
    let c = this.cache.get(k) as number | undefined
    if (c === undefined) {
      const ws: [string, number][] = []
      for (const [o, x] of this.opp.get(team) ?? []) if (x[0]) ws.push([o, x[0]])
      this.cache.set(k, (c = this.oppPctSum(ws)))
    }
    return c
  }

  /** Combined win percentage of every opponent (once per game). */
  sos(team: string): number {
    const k = `sos|${team}`
    let c = this.cache.get(k) as number | undefined
    if (c === undefined) {
      const ws: [string, number][] = []
      for (const [o, x] of this.opp.get(team) ?? []) ws.push([o, x[2]])
      this.cache.set(k, (c = this.oppPctSum(ws)))
    }
    return c
  }

  points(team: string): [number, number] {
    return [this.pf.get(team) ?? 0, this.pa.get(team) ?? 0]
  }

  netPoints(team: string, opps?: Iterable<string>): number {
    if (opps === undefined) return (this.pf.get(team) ?? 0) - (this.pa.get(team) ?? 0)
    const nd = this.net.get(team)
    let s = 0
    for (const o of opps) s += nd?.get(o) ?? 0
    return s
  }

  /** [league, conference] rank sums (points-for rank + points-against rank; lower is better; level clubs share a rank). */
  pointsRanks(): [Map<string, number>, Map<string, number>] {
    let c = this.cache.get('ranks') as [Map<string, number>, Map<string, number>] | undefined
    if (!c) {
      const teams = this.teams
      const league = rankSum(teams, this.pf, this.pa)
      const conf = new Map<string, number>()
      for (const members of Object.values(CONFERENCE_SET)) {
        for (const [t, v] of rankSum(teams.filter((t) => members.has(t)), this.pf, this.pa)) conf.set(t, v)
      }
      this.cache.set('ranks', (c = [league, conf]))
    }
    return c
  }
}

function rankSum(teams: string[], pf: Map<string, number>, pa: Map<string, number>): Map<string, number> {
  const f = teams.map((t) => pf.get(t) ?? 0)
  const a = teams.map((t) => pa.get(t) ?? 0)
  return new Map(teams.map((t, i) => [t, 2 + f.filter((x) => x > f[i]).length + a.filter((x) => x < a[i]).length]))
}

export function without(s: Iterable<string>, drop: string[]): Set<string> {
  const out = new Set(s)
  for (const d of drop) out.delete(d)
  return out
}
