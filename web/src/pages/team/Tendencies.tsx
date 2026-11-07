import { TendencyRow, TipNote, TipRow, TipTitle, type TendencyRowData } from '../../charts'
import { FinePrint } from '../../components/FinePrint'
import { DataTable, td, th } from '../../components/ui'
import type { TeamFile, TeamMetric, TeamUnit } from '../../data/contract'
import { teamDotVars } from '../../lib/teamColors'
import { ordinal } from '../league/helpers'
import { Block } from './Block'
import { READ_TEXT, callerChange, changeLine, fmtRate, leanText, placeOf, read, sortRows, starterLines, unitLine } from './tendencies'

const span = (first: number, last: number) => (first === last ? `${first}` : `${first}–${String(last).slice(-2)}`)

function toRow(m: TeamMetric, file: TeamFile, unit: TeamUnit): TendencyRowData {
  const r = read(m)
  const chip = r ? READ_TEXT[r] : leanText(m)
  const o = m.observed
  const last = m.team_last
  const past = m.caller_past
  const caller = unit.caller?.confirmed ? unit.caller.name : 'The caller'
  return {
    key: m.metric,
    label: (
      <span className="flex min-w-0">
        <span className="truncate">{m.label}</span>
        {chip && <span className="shrink-0 whitespace-pre text-ink-3">{` · ${chip.toLowerCase()}`}</span>}
      </span>
    ),
    summary: `${m.label}: ${o ? `${fmtRate(o.rate, m.unit)}, ${ordinal(o.rank)} of ${o.of}` : last ? `${fmtRate(last.rate, m.unit)} in ${last.season}` : 'no data'}${chip ? `, ${chip.toLowerCase()}` : ''}`,
    now: o?.pct ?? null,
    past: past?.pct ?? null,
    last: last?.pct ?? null,
    value: o ? fmtRate(o.rate, m.unit) : last ? fmtRate(last.rate, m.unit) : '–',
    sub: o ? `${ordinal(o.rank)} of ${o.of}` : last ? `in ${last.season}` : '',
    ends: m.lo === 'less' ? undefined : [m.lo, m.hi],
    tip: (
      <>
        <TipTitle>{m.label}</TipTitle>
        {o && <TipRow value={`${fmtRate(o.rate, m.unit)}, ${ordinal(o.rank)}`} label={`${file.team} this season`} />}
        {past && <TipRow value={`about ${ordinal(placeOf(past.pct))}`} label={`${caller}'s past, ${span(past.first, file.season - 1)}`} />}
        {last && <TipRow value={`${fmtRate(last.rate, m.unit)}, ${ordinal(last.rank)}`} label={`${file.team} in ${last.season}`} />}
        <TipNote>{m.help}</TipNote>
      </>
    ),
  }
}

function Legend({ color, caller }: { color: string; caller: string | null }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-ink-2">
      <span className="inline-flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: color }} /> This season</span>
      {caller && <span className="inline-flex items-center gap-1"><span className="inline-block h-2 w-2 rotate-45 border-2 border-[var(--text-secondary)]" /> {caller}'s past</span>}
      <span className="inline-flex items-center gap-1">
        <svg aria-hidden width="13" height="11" viewBox="0 0 13 11"><path d="M6.5 0.5 L12.5 10.5 H0.5 Z" fill="var(--text-secondary)" /></svg> Last season
      </span>
      <span className="inline-flex items-center gap-1">
        <svg aria-hidden width="4" height="12" viewBox="0 0 4 12"><line x1="2" x2="2" y1="0" y2="12" stroke="var(--text-muted)" strokeDasharray="2 3" /></svg> League average
      </span>
      <span className="text-ink-3">Further right: more of it</span>
    </div>
  )
}

function Numbers({ rows, file }: { rows: TeamMetric[]; file: TeamFile }) {
  return (
    <DataTable>
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr>
            <th scope="col" className={th}>Measure</th>
            <th scope="col" className={th}>{file.season}</th>
            <th scope="col" className={th}>Caller's past</th>
            <th scope="col" className={th}>{file.season - 1}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => (
            <tr key={m.metric}>
              <td className={td}>{m.label}</td>
              <td className={td}>{m.observed ? `${fmtRate(m.observed.rate, m.unit)} (${ordinal(m.observed.rank)})` : '–'}</td>
              <td className={td}>{m.caller_past ? `about ${ordinal(placeOf(m.caller_past.pct))}` : '–'}</td>
              <td className={td}>{m.team_last ? `${fmtRate(m.team_last.rate, m.unit)} (${ordinal(m.team_last.rank)})` : '–'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </DataTable>
  )
}

const SIDES = [['off', 'Offense'], ['def', 'Defense']] as const

/** This season against the play-caller's own past and the team's last season (ADR 0022, revised 2026-11-07). */
export function Tendencies({ file }: { file: TeamFile }) {
  const color = 'var(--team-home)' // set per theme by [data-matchup]
  const starters = starterLines(file)
  return (
    <div data-matchup style={teamDotVars(file.team)} className="flex flex-col gap-6">
      {SIDES.map(([side, name]) => {
        const unit = file.units[side]
        const change = callerChange(file, side)
        const hasPast = unit.live.some((m) => m.caller_past != null)
        const caller = hasPast ? (unit.caller?.confirmed ? unit.caller.name : 'The caller') : null
        const rows = sortRows(unit.live)
        return (
          <Block key={side} title={`${name} this season`} line={change ? changeLine(change, file.through_week) : unitLine(unit, file.team)}>
            {side === 'off' && starters.map((s) => <p key={s} className="m-0 text-[13px] text-ink-3">{s}</p>)}
            <Legend color={color} caller={caller} />
            <TendencyRow rows={rows.map((m) => toRow(m, file, unit))} color={color} />
            <Numbers rows={rows} file={file} />
          </Block>
        )
      })}
      {SIDES.map(([side, name]) => {
        const unit = file.units[side]
        const rows = [...unit.charted].sort((a, b) => a.label.localeCompare(b.label))
        const waiting = rows.some((m) => !m.observed)
        return (
          <Block key={side} title={`${name}: what to watch for`} line={side === 'off' && waiting ? `Charted once a year, so ${file.season} isn't in yet. Here's the caller's past and last season to compare with.` : undefined}>
            <TendencyRow rows={rows.map((m) => toRow(m, file, unit))} color={color} />
            <Numbers rows={rows} file={file} />
          </Block>
        )
      })}
      <FinePrint label="How to read this">
        <ul className="list-disc space-y-1.5 pl-5">
          <li>Every mark is a place in the league that season: the dashed line is the league average, further right is more of it. More isn't better: these describe what a team does.</li>
          <li>The diamond is the play-caller's own past, averaged over his earlier seasons with recent ones counting most, wherever he called plays. None means no past as a play-caller in our data.</li>
          <li>"Matches" means this season is within about five places of that mark.</li>
          <li>"Watch the caller" or "watch last year" says which mark has predicted better when a caller moved before, from 2017 to 2025. No tag means neither did much better than a guess.</li>
          <li>Personnel, coverage, time to throw and pressure come from charting published each spring, so this season's dot appears then.</li>
        </ul>
      </FinePrint>
    </div>
  )
}
