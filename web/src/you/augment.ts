/**
 * Add the reader's line to the data a page reads (ADR 0034): `models.you` beside the published
 * lines, and on a game file `contributions.you` for the breakdown charts. A game whose file has no
 * composites (older data, or no headline row yet) gets no "you".
 */
import type { Contribution, Game, GameRow, Slate } from '../data/contract'
import { YOU, type YouLine } from './current'
import { contributionOf, scoreLine } from './line'

const r = (x: number, nd: number) => Math.round(x * 10 ** nd) / 10 ** nd

export function withYou<T extends GameRow>(g: T, you: YouLine | null): T {
  const comp = g.composites
  if (!you || !comp) return g
  const s = scoreLine(you.line, comp)
  const mk = g.market?.p_home
  const head = g.models.student
  const pick = {
    p_home: r(s.p_home, 4),
    spread_home: r(s.spread_home, 1),
    status: head?.status ?? 'preview',
    lock_ts: comp.as_of,
    divergence: mk == null ? null : r(s.p_home - mk, 4),
  } as const
  const out = { ...g, models: { ...g.models, [YOU]: pick } }
  if ('contributions' in g && g.contributions) {
    const c = g.contributions as Record<string, Contribution>
    ;(out as unknown as Game).contributions = { ...c, [YOU]: contributionOf(s) }
  }
  return out
}

export const slateWithYou = (s: Slate, you: YouLine | null): Slate =>
  you ? { ...s, games: s.games.map((g) => withYou(g, you)) } : s
