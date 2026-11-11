/**
 * One side of a matchup (ADR 0028): the offense against the defense it faces, one row per situation. The unit
 * that chooses a situation (the defense blitzes, the offense motions) has a habit, drawn on the league's band of
 * habits with a dot in its team's colour and a tick for how often the other unit has seen it. The other unit's
 * shrunk result in that situation is a number beside it; the edge is a signed pill in the colour of the team it
 * favours. Context rows (no edge) show the result alone, with the reason in the tooltip. Every figure comes from
 * the JSON; this file only formats and places marks. On a phone the result column folds into the tooltip.
 */
import type { CSSProperties } from 'react'
import { TipNote, TipRow, TipTitle, useChartTip } from './ChartTip'
import type { MatchupRow } from '../data/contract'
import { pct } from '../lib/format'

export type SplitDef = { label: string; definition: string }

type Side = { offense: string; defense: string; rows: MatchupRow[] }

const COLS = 'grid-cols-[minmax(0,1fr)_4.5rem_3.5rem] sm:grid-cols-[minmax(0,9rem)_minmax(0,1fr)_5.5rem_5.5rem_3.5rem]'

const minus = (x: number) => (x < 0 ? '−' : x > 0 ? '+' : '')
/** EPA per play, signed, two places. */
const fmtEpa = (x: number | null | undefined) => (x == null ? '–' : `${minus(Math.round(x * 100) / 100)}${Math.abs(x).toFixed(2)}`)
const RELIABILITY: Record<MatchupRow['reliability'], string> = { noise: 'noise', some: 'some', stable: 'stable' }

type Group = { key: string; title: string; rows: MatchupRow[] }

function groups(side: Side): Group[] {
  const by = (f: (r: MatchupRow) => boolean) => side.rows.filter(f)
  const all: Group[] = [
    { key: 'defense', title: `${side.defense} defense chooses`, rows: by((r) => r.has_edge && r.chooser === 'defense') },
    { key: 'offense', title: `${side.offense} offense chooses`, rows: by((r) => r.has_edge && r.chooser === 'offense') },
    { key: 'context', title: 'Context (no edge)', rows: by((r) => !r.has_edge) },
  ]
  return all.filter((g) => g.rows.length > 0)
}

export function MatchupGrid({ side, home, away, defs }: { side: Side; home: string; away: string; defs: Record<string, SplitDef> }) {
  const { box, at, bind, card } = useChartTip()
  const colorOf = (team: string) => (team === home ? 'var(--team-home)' : team === away ? 'var(--team-away)' : 'var(--text-secondary)')
  const hovered = side.rows.find((r) => r.split === at?.key)
  const chooserTeam = (r: MatchupRow) => (r.chooser === 'defense' ? side.defense : r.chooser === 'offense' ? side.offense : null)
  const otherTeam = (r: MatchupRow) => (r.chooser === 'defense' ? side.offense : r.chooser === 'offense' ? side.defense : null)
  return (
    <div data-testid="matchup-grid" className="w-full">
      <h3 className="mb-2 text-[15px] font-semibold">Situations: {side.offense} offense vs {side.defense} defense</h3>
      <div ref={box} className="relative">
        <div className={`grid ${COLS} gap-x-3 border-b border-line px-1 pb-1 text-[11px] text-ink-3`} aria-hidden>
          <span>Situation</span>
          <span className="hidden sm:block">Habit on the league's range (tick: faced)</span>
          <span className="hidden text-right sm:block">Other unit's result, EPA/play</span>
          <span className="text-right">Edge, pts/game</span>
          <span className="text-right">Reliability</span>
        </div>
        {groups(side).map((grp) => {
          const rows = grp.rows.map((r) => {
              const def = defs[r.split]
              const label = def?.label ?? r.label
              const on = hovered?.split === r.split
              const team = chooserTeam(r)
              const favTeam = r.favours === 'offense' ? side.offense : r.favours === 'defense' ? side.defense : null
              const pill = r.has_edge && favTeam && r.edge_pts_pg != null
              return (
                <div
                  key={r.split}
                  data-testid={`row-${r.split}`}
                  data-edge={pill ? 'yes' : 'no'}
                  className={`grid ${COLS} items-center gap-x-3 rounded px-1 py-1.5 ${on ? 'bg-surface-2' : ''}`}
                  {...bind(r.split)}
                >
                  <span className={`truncate text-[13px] ${r.has_edge ? 'text-ink' : 'text-ink-3'}`}>{label}</span>
                  {team && r.opp_rate != null ? (
                    <span className="order-last col-span-3 pt-1.5 sm:order-none sm:col-span-1 sm:pt-0"><HabitBand r={r} color={colorOf(team)} /></span>
                  ) : (
                    <span className="hidden text-ink-3 sm:block">–</span>
                  )}
                  <span className="tabular hidden text-right text-[13px] text-ink-2 sm:block">{fmtEpa(r.shrunk_gap)}</span>
                  <span className="text-right">
                    {pill && favTeam ? (
                      <span
                        data-testid="edge-pill"
                        data-team={favTeam}
                        className="tabular inline-block whitespace-nowrap rounded-full border px-2 py-0.5 text-[12px] font-medium text-ink"
                        style={{ borderColor: colorOf(favTeam), background: `color-mix(in srgb, ${colorOf(favTeam)} 18%, transparent)` } as CSSProperties}
                      >
                        +{Math.abs(r.edge_pts_pg!).toFixed(2)} {favTeam}
                      </span>
                    ) : null}
                  </span>
                  <span className="text-right text-[12px] text-ink-3" data-reliability={r.reliability}>({RELIABILITY[r.reliability]})</span>
                </div>
              )
            })
          // context rows (no edge) fold away so the scheme matchups lead
          return grp.key === 'context' ? (
            <details key={grp.key} role="group" aria-label={grp.title} data-testid="context-rows">
              <summary className="cursor-pointer px-1 pb-0.5 pt-3 text-[12px] font-medium text-ink-2">
                {grp.title}: {grp.rows.length} more situations
              </summary>
              {rows}
            </details>
          ) : (
            <div key={grp.key} role="group" aria-label={grp.title}>
              <div className="px-1 pb-0.5 pt-3 text-[12px] font-medium text-ink-2">{grp.title}</div>
              {rows}
            </div>
          )
        })}
        {card(
          hovered && (
            <>
              <TipTitle note={defs[hovered.split]?.definition}>{defs[hovered.split]?.label ?? hovered.label}</TipTitle>
              {chooserTeam(hovered) && hovered.opp_rate != null && (
                <TipRow color={colorOf(chooserTeam(hovered)!)} value={pct(hovered.opp_rate, 1)} label={`${chooserTeam(hovered)} ${hovered.chooser} habit; the league's middle half is ${pct(hovered.opp_rate_q1)} to ${pct(hovered.opp_rate_q3)}, most teams ${pct(hovered.opp_rate_lo)} to ${pct(hovered.opp_rate_hi)}`} />
              )}
              {otherTeam(hovered) && hovered.rate_faced != null && <TipRow value={pct(hovered.rate_faced, 1)} label={`${otherTeam(hovered)} has faced it this season`} />}
              <TipRow value={fmtEpa(hovered.shrunk_gap)} label={`EPA per play, shrunk (${hovered.n_with} plays with, ${hovered.n_without} without${hovered.epa_with != null && hovered.epa_without != null ? `; raw ${fmtEpa(hovered.epa_with)} vs ${fmtEpa(hovered.epa_without)}` : ''}${hovered.league_gap != null ? `; league ${fmtEpa(hovered.league_gap)}` : ''})`} />
              {hovered.has_edge && hovered.edge_pts_pg != null && hovered.favours && (
                <TipRow value={`+${Math.abs(hovered.edge_pts_pg).toFixed(2)} pts`} label={`a game, favours the ${hovered.favours} (${hovered.favours === 'offense' ? side.offense : side.defense})`} />
              )}
              <TipRow value={hovered.reliability} label="reliability of this kind of number" />
              {hovered.note && <TipNote>{hovered.note}</TipNote>}
            </>
          ),
        )}
      </div>
    </div>
  )
}

function HabitBand({ r, color }: { r: MatchupRow; color: string }) {
  const vals = [r.opp_rate_lo, r.opp_rate_hi, r.opp_rate, r.rate_faced].filter((v): v is number => v != null)
  const lo = Math.min(...vals)
  const hi = Math.max(...vals)
  const span = hi - lo || 1
  const at = (v: number) => `${((v - lo) / span) * 100}%`
  const bar = (a: number | null, b: number | null) => (a != null && b != null ? { left: at(a), width: `max(2px, calc(${at(b)} - ${at(a)}))` } : null)
  const outer = bar(r.opp_rate_lo, r.opp_rate_hi)
  const core = bar(r.opp_rate_q1, r.opp_rate_q3)
  return (
    <span data-testid="habit-band" className="relative mx-2 block h-4">
      {outer && <span className="absolute top-[1px] h-[14px] rounded-[3px]" style={{ ...outer, background: 'var(--band)' }} />}
      {core && <span className="absolute top-[1px] h-[14px]" style={{ ...core, background: 'var(--band-strong)' }} />}
      {r.opp_rate_med != null && <span className="absolute top-0 h-4 w-[1.5px]" style={{ left: at(r.opp_rate_med), background: 'var(--text-muted)' }} />}
      {r.rate_faced != null && <span data-testid="faced-tick" className="absolute -top-[2px] h-5 w-[2px] -translate-x-1/2 rounded-full" style={{ left: at(r.rate_faced), background: 'var(--text-primary)' }} />}
      {r.opp_rate != null && <span data-testid="habit-dot" className="absolute top-[2px] h-3 w-3 -translate-x-1/2 rounded-full border-2 border-[var(--surface-1)]" style={{ left: at(r.opp_rate), background: color }} />}
    </span>
  )
}
