/**
 * What you'll see (Matchups redesign, 2026-11-12): one light line per habit (who does it, a four-step meter of
 * where it sits among the league's teams by quartile, and a pill for which side the habit has favoured); the
 * rate, how the other unit did with and without it, the points and the evidence label are in the hover card
 * (Austin: too wordy as text). Habits repeat week to week; results in a situation barely do, so the verdict is a
 * word and the evidence label stays visible. Every number is read from the JSON (`matchups.sides[].rows`, and
 * the offense's pass rate from `tendencies`); this file only words and places them.
 */
import { TipNote, TipRow, TipTitle, useChartTip } from './ChartTip'
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

function Pill({ team, color }: { team: string | null; color: string | null }) {
  return team && color ? (
    <span data-testid="habit-verdict" data-team={team} className="shrink-0 rounded-full border px-1.5 text-[11px] font-medium text-ink" style={{ borderColor: color }}>
      {team} edge
    </span>
  ) : (
    <span data-testid="habit-verdict" className="shrink-0 rounded-full border border-line px-1.5 text-[11px] text-ink-3">
      even
    </span>
  )
}

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
  const { box, at, bind, card } = useChartTip()
  const habits = rows.filter((r) => r.has_edge && r.chooser !== 'neither' && r.opp_rate != null)
  // the defense's habits first (they choose against this offense), then the offense's
  habits.sort((a, b) => (a.chooser === b.chooser ? 0 : a.chooser === 'defense' ? -1 : 1))
  if (habits.length === 0 && !pass) return null
  const hovered = habits.find((r) => r.split === at?.key)
  const who = (r: MatchupRow) => ({
    chooser: r.chooser === 'defense' ? defense : offense,
    other: r.chooser === 'defense' ? offense : defense,
    otherUnit: r.chooser === 'defense' ? 'offense' : 'defense',
    fav: r.favours === 'offense' ? offense : r.favours === 'defense' ? defense : null,
  })
  const even = (r: MatchupRow) => r.edge_pts_pg == null || Math.abs(r.edge_pts_pg) < EVEN
  return (
    <div ref={box} className="relative">
      <ul data-testid="habit-list" className="m-0 list-none p-0">
        {pass && (
          <li data-testid="habit-pass" className="flex items-center justify-between gap-3 border-b border-line py-1.5 text-[13px]">
            <span>
              {pass.team} passes <span className="tabular text-ink-2">{pct(pass.rate)}</span>
              <span className="text-ink-3"> · league {pct(pass.league)}</span>
            </span>
          </li>
        )}
        {habits.map((r) => {
          const w = who(r)
          const fav = even(r) ? null : w.fav
          return (
            <li
              key={r.split}
              data-testid={`habit-${r.split}`}
              className={`flex cursor-default items-center gap-3 rounded border-b border-line px-1 py-1.5 text-[13px] ${hovered?.split === r.split ? 'bg-surface-2' : ''}`}
              {...bind(r.split)}
            >
              <span className="min-w-0 flex-1 truncate">
                {w.chooser} {VERB[r.split] ?? r.label.toLowerCase()}
              </span>
              <Meter q={quartile(r)} color={colorOf(w.chooser)} />
              <Pill team={fav} color={fav ? colorOf(fav) : null} />
            </li>
          )
        })}
      </ul>
      {card(
        hovered &&
          (() => {
            const w = who(hovered)
            const q = quartile(hovered)
            return (
              <>
                <TipTitle note={`${w.chooser}'s ${hovered.chooser}`}>{hovered.label}</TipTitle>
                <TipRow color={colorOf(w.chooser)} value={pct(hovered.opp_rate)} label={`${OF[hovered.split] ?? 'of plays'}${q ? `, ${WORD[q]}` : ''}`} />
                {hovered.epa_with != null && hovered.epa_without != null && (
                  <TipRow value={`${signed(hovered.epa_with)} / ${signed(hovered.epa_without)}`} label={`${w.other}'s ${w.otherUnit}, EPA a play with it / without (${hovered.n_with} plays with)`} />
                )}
                <TipRow
                  value={even(hovered) || !w.fav ? 'about even' : `${Math.abs(hovered.edge_pts_pg!).toFixed(2)} pts`}
                  label={even(hovered) || !w.fav ? 'between the two' : `a game toward ${w.fav}`}
                />
                <TipNote>
                  <span data-reliability={hovered.reliability}>{EVIDENCE[hovered.reliability]}</span>: how a team did in a situation barely repeats week to week.
                </TipNote>
              </>
            )
          })(),
      )}
    </div>
  )
}
