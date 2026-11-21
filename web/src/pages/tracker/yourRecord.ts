/**
 * The reader's own line scored over the season so far (ADR 0034), in the browser. Pure: a CustomSeason
 * (composites as of the Student's graded lock) and a saved line in, three records out (You, the Student,
 * the market), each on the games where that line has a probability. Unofficial: never locked or graded.
 */
import type { CustomGame, CustomSeason } from '../../data/contract'
import { scoreLine } from '../../you/line'
import type { YouLine } from '../../you/current'

const P_CLIP = 1e-6
export const LINES = ['you', 'student', 'market'] as const
export type RecordLine = (typeof LINES)[number]

export interface LineRecord {
  /** games this line was scored on */
  n: number
  /** side picks that were right; a pick of exactly 0.5 counts for nobody */
  right: number
  /** mean log loss, null with no games */
  logLoss: number | null
}

export type Records = Record<RecordLine, LineRecord>
export interface WeekPoint {
  week: number
  you: number | null
  student: number | null
  market: number | null
}

export interface YourRecord {
  all: Records
  /** only games that kicked off after the line was saved: the out-of-sample part */
  since: Records
  /** cumulative mean log loss by week, per line */
  weeks: WeekPoint[]
}

const clip = (p: number) => Math.min(Math.max(p, P_CLIP), 1 - P_CLIP)
const loss = (p: number, homeWon: number) => -Math.log(homeWon === 1 ? clip(p) : 1 - clip(p))
const isRight = (p: number, homeWon: number) => (p > 0.5 && homeWon === 1) || (p < 0.5 && homeWon === 0)

type Acc = { n: number; right: number; sum: number }
const fresh = (): Record<RecordLine, Acc> => ({ you: { n: 0, right: 0, sum: 0 }, student: { n: 0, right: 0, sum: 0 }, market: { n: 0, right: 0, sum: 0 } })
const finish = (a: Record<RecordLine, Acc>): Records => {
  const f = (x: Acc): LineRecord => ({ n: x.n, right: x.right, logLoss: x.n ? x.sum / x.n : null })
  return { you: f(a.you), student: f(a.student), market: f(a.market) }
}
const add = (a: Acc, p: number, g: CustomGame) => {
  a.n += 1
  a.sum += loss(p, g.home_won)
  if (isRight(p, g.home_won)) a.right += 1
}

export function yourRecord(season: CustomSeason, you: Pick<YouLine, 'line' | 'savedAt'>): YourRecord {
  const saved = Date.parse(you.savedAt)
  const all = fresh()
  const since = fresh()
  const running = fresh()
  const byWeek = new Map<number, CustomGame[]>()
  for (const g of season.games) byWeek.set(g.week, [...(byWeek.get(g.week) ?? []), g])
  const weeks: WeekPoint[] = []
  for (const week of [...byWeek.keys()].sort((a, b) => a - b)) {
    for (const g of byWeek.get(week)!) {
      const after = g.kickoff_utc != null && Date.parse(g.kickoff_utc) > saved
      const ps: Record<RecordLine, number | null> = { you: scoreLine(you.line, g).p_home, student: g.p_student, market: g.p_market }
      for (const k of LINES) {
        const p = ps[k]
        if (p == null) continue
        add(all[k], p, g)
        add(running[k], p, g)
        if (after) add(since[k], p, g)
      }
    }
    const at = (k: RecordLine) => (running[k].n ? running[k].sum / running[k].n : null)
    weeks.push({ week, you: at('you'), student: at('student'), market: at('market') })
  }
  return { all: finish(all), since: finish(since), weeks }
}
