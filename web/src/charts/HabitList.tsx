/**
 * What you'll see (Matchups redesign, 2026-11-12): the choosing unit's habits in words, a four-step meter of
 * where the habit sits among the league's teams (by quartile), and one soft line on how the other unit has
 * done with and without it. Habits repeat week to week; results in a situation barely do, so the verdict is a
 * word and the evidence label stays visible. Every number is read from the JSON (`matchups.sides[].rows`, and
 * the offense's pass rate from `tendencies`); this file only words and places them.
 */
import type { MatchupRow } from '../data/contract'
import { pct } from '../lib/format'
import { quartile } from '../lib/rank'

const VERB: Record<string, string> = {
  blitz: 'blitzes',
  box_light: 'plays a light box against the run',
  box_heavy: 'stacks the box against the run',
  play_action: 'uses play action',
  motion: 'moves before the snap',
  screen: 'throws screens',
  rpo: 'runs run-pass options',
}
const OF: Record<string, string> = {
  blitz: 'of dropbacks',
  box_light: 'of runs',
  box_heavy: 'of runs',
}
const EVIDENCE: Record<MatchupRow['reliability'], string> = { noise: 'thin evidence', some: 'some evidence', stable: 'solid evidence' }
/** Below this many points a game, the edge reads "about even". */
const EVEN = 0.05

const WORD = ['', 'less than most teams', 'a bit less than the middle team', 'a bit more than the middle team', 'more than most teams']

const signed = (x: number) => `${x < 0 ? '−' : '+'}${Math.abs(x).toFixed(2)}`

function Meter({ q, color }: { q: number | null; color: string }) {
  return (
    <span className="flex shrink-0 gap-[2px]" role="img" aria-label={q ? `quartile ${q} of 4` : 'no league range'}>
      {[1, 2, 3, 4].map((i) => (
        <i key={i} className="block h-2 w-3.5 rounded-sm" style={{ background: q != null && i <= q ? color : 'var(--band)' }} />
      ))}
    </span>
  )
}

export type PassHabit = { team: string; rate: number; league: number }

export function HabitList({
  rows,
  offense,
  defense,
  colorOf,
  pass,
}: {
  rows: MatchupRow[]
  offense: string
  defense: string
  colorOf: (team: string) => string
  pass?: PassHabit | null
}) {
  const habits = rows.filter((r) => r.has_edge && r.chooser !== 'neither' && r.opp_rate != null)
  // the defense's habits first (they choose against this offense), then the offense's
  habits.sort((a, b) => (a.chooser === b.chooser ? 0 : a.chooser === 'defense' ? -1 : 1))
  if (habits.length === 0 && !pass) return null
  return (
    <ul data-testid="habit-list" className="m-0 list-none p-0">
      {pass && (
        <li data-testid="habit-pass" className="flex items-baseline justify-between gap-3 border-b border-line py-2 text-[13px]">
          <span>
            <span className="font-semibold">
              {pass.team} passes on {pct(pass.rate)} of plays
            </span>{' '}
            <span className="text-ink-2">(the league: {pct(pass.league)})</span>
          </span>
        </li>
      )}
      {habits.map((r) => {
        const chooser = r.chooser === 'defense' ? defense : offense
        const other = r.chooser === 'defense' ? offense : defense
        const otherUnit = r.chooser === 'defense' ? 'offense' : 'defense'
        const q = quartile(r)
        const fav = r.favours === 'offense' ? offense : r.favours === 'defense' ? defense : null
        const e = r.edge_pts_pg
        const verdict = e == null || !fav || Math.abs(e) < EVEN ? 'about even' : `edge ${fav}, ${Math.abs(e).toFixed(2)} pts a game`
        const result =
          r.epa_with != null && r.epa_without != null
            ? `${other}'s ${otherUnit}: ${signed(r.epa_with)} EPA a play with it, ${signed(r.epa_without)} without (${r.n_with} plays)`
            : `${other}'s ${otherUnit}: ${r.n_with} plays with it so far`
        return (
          <li key={r.split} data-testid={`habit-${r.split}`} className="border-b border-line py-2 text-[13px]">
            <div className="flex items-baseline justify-between gap-3">
              <span>
                <span className="font-semibold">
                  {chooser} {VERB[r.split] ?? r.label.toLowerCase()}
                </span>{' '}
                <span className="text-ink-2">
                  · {pct(r.opp_rate)} {OF[r.split] ?? 'of plays'}, {q ? WORD[q] : ''}
                </span>
              </span>
              <Meter q={q} color={colorOf(chooser)} />
            </div>
            <div className="mt-0.5 text-[12px] text-ink-2">
              {result}.{' '}
              <span data-testid="habit-verdict" className="font-medium text-ink">
                {verdict[0].toUpperCase() + verdict.slice(1)}
              </span>{' '}
              <span data-reliability={r.reliability} className="ml-1 inline-block rounded-full border border-line px-1.5 text-[10.5px] text-ink-3">
                {EVIDENCE[r.reliability]}
              </span>
            </div>
          </li>
        )
      })}
    </ul>
  )
}
