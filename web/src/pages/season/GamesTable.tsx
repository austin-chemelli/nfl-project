import { useMemo, useState } from 'react'
import { Help } from '../../components/Help'
import { td, th } from '../../components/ui'
import type { Meta } from '../../data/contract'
import type { SeasonGame } from '../../diy'
import { pct, ptsToward } from '../../lib/format'
import { groupName, helpFor } from '../../lib/meta'
import { resultText } from './format'

type Key = 'week' | 'game' | 'p' | 'market' | 'result' | 'you' | 'mkt' | 'push'

const value = (g: SeasonGame, k: Key): number | string => {
  switch (k) {
    case 'week': return g.week
    case 'game': return `${g.away} @ ${g.home}`
    case 'p': return g.p
    case 'market': return g.market_p ?? -1
    case 'result': return g.result == null ? 0 : g.result
    case 'you': return g.correct ? 1 : 0
    case 'mkt': return g.market_correct == null ? -1 : g.market_correct ? 1 : 0
    case 'push': return Math.abs(g.push_pts)
  }
}

const mark = (ok: boolean | null) => (ok == null ? '–' : ok ? '✓' : '✗')

const COLS: { key: Key; label: string; help?: string }[] = [
  { key: 'week', label: 'Week' },
  { key: 'game', label: 'Game' },
  { key: 'p', label: 'Your home win', help: 'Your chance that the home team wins, after calibration.' },
  { key: 'market', label: 'Market home win', help: "The betting market's chance for the home team, vig removed. The reference line, never an input." },
  { key: 'result', label: 'Result' },
  { key: 'you', label: 'You', help: 'Did the team you gave over 50% win?' },
  { key: 'mkt', label: 'Market', help: "Did the market's favorite win?" },
  { key: 'push', label: 'Biggest push', help: 'The group that moved your probability the most, in points of win probability (how much lower your number would be without it).' },
]

/** Every game, sortable by clicking a column header. */
export function GamesTable({ games, meta }: { games: SeasonGame[]; meta: Meta }) {
  const [sort, setSort] = useState<{ key: Key; dir: 1 | -1 }>({ key: 'week', dir: 1 })
  const rows = useMemo(() => {
    const out = [...games]
    out.sort((a, b) => {
      const x = value(a, sort.key), y = value(b, sort.key)
      const c = typeof x === 'string' ? x.localeCompare(y as string) : (x as number) - (y as number)
      return c * sort.dir || a.week - b.week
    })
    return out
  }, [games, sort])
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[46rem] border-collapse text-[14px]">
        <thead>
          <tr>
            {COLS.map((c) => (
              <th key={c.key} className={th} aria-sort={sort.key === c.key ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
                <button type="button" className="uppercase tracking-wide hover:text-ink" onClick={() => setSort((s) => ({ key: c.key, dir: s.key === c.key ? (s.dir === 1 ? -1 : 1) : 1 }))}>
                  {c.label}{sort.key === c.key ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}
                </button>
                {c.help && <Help text={c.help} />}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((g) => (
            <tr key={g.game_id}>
              <td className={`${td} tabular`}>{g.week}</td>
              <td className={`${td} whitespace-nowrap`}>{g.away} @ {g.home}</td>
              <td className={`${td} tabular`}>{pct(g.p, 1)}</td>
              <td className={`${td} tabular`}>{pct(g.market_p, 1)}</td>
              <td className={`${td} whitespace-nowrap`}>{resultText(g)}</td>
              <td className={td} aria-label={g.correct ? 'right' : 'wrong'}>{mark(g.correct)}</td>
              <td className={td}>{mark(g.market_correct)}</td>
              <td className={td}>
                {g.push_group == null ? <span className="text-ink-3">no strong push</span> : (
                  <>
                    <Help text={helpFor(meta, g.push_group)}>{groupName(meta, g.push_group)}</Help>: {ptsToward(g.push_pts, g.home, g.away)}
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
