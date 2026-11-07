import { ExpectRow, TipNote, TipRow, TipTitle, type ExpectRowData } from '../../charts'
import { FinePrint } from '../../components/FinePrint'
import { DataTable, td, th } from '../../components/ui'
import type { TeamFile, TeamMetric, TeamUnit } from '../../data/contract'
import { teamDotVars } from '../../lib/teamColors'
import { ordinal } from '../league/helpers'
import { Block } from './Block'
import { VERDICT_TEXT, basis, callerChange, changeLine, expectWords, fmtRate, sortRows, starterLines, unitLine, verdict } from './tendencies'

const pct = (v: number) => `${Math.round(100 * Math.min(1, Math.max(0, v)))}%`

function toRow(m: TeamMetric, file: TeamFile, unit: TeamUnit, mixed: boolean): ExpectRowData {
  const v = verdict(m, mixed)
  const e = v === 'no_range' ? null : m.expected // nothing measured: the team's last season stands alone
  const o = m.observed
  const last = m.team_last
  const [word, than] = expectWords(m)
  const caller = unit.caller?.confirmed ? unit.caller.name : null
  const said = v === 'waiting' ? '' : ` · ${VERDICT_TEXT[v].toLowerCase()}`
  const where = o ? `${fmtRate(o.rate, m.unit)}, ${ordinal(o.rank)} of ${o.of}` : e ? `expected ${word.toLowerCase()} ${than}` : last ? `${fmtRate(last.rate, m.unit)} in ${last.season}` : 'no data'
  return {
    key: m.metric,
    label: (
      <span className="flex min-w-0">
        <span className="truncate">{m.label}</span>
        {said && <span className="shrink-0 whitespace-pre text-ink-3">{said}</span>}
      </span>
    ),
    summary: `${m.label}: ${where}${said.replace(' · ', ', ')}`,
    expected: e?.pct ?? null,
    miss: e?.miss ?? null,
    rough: v === 'rough',
    observed: o?.pct ?? null,
    last: last?.pct ?? null,
    value: o ? fmtRate(o.rate, m.unit) : e ? word : last ? fmtRate(last.rate, m.unit) : '–',
    sub: o ? `${ordinal(o.rank)} of ${o.of}` : e ? than : last ? `${last.season}: ${ordinal(last.rank)}` : '',
    ends: m.lo === 'less' ? undefined : [m.lo, m.hi],
    tip: (
      <>
        <TipTitle>{m.label}</TipTitle>
        {o && <TipRow value={`${fmtRate(o.rate, m.unit)}, ${ordinal(o.rank)}`} label="So far" />}
        {e?.miss != null && <TipRow value={`${pct(e.pct - e.miss)} to ${pct(e.pct + e.miss)}`} label="Expected, share of teams below" />}
        {last && <TipRow value={`${fmtRate(last.rate, m.unit)}, ${ordinal(last.rank)}`} label={`Team in ${last.season}`} />}
        <TipNote>{basis(m, file, caller) || m.help}</TipNote>
      </>
    ),
  }
}

function Legend({ color }: { color: string }) {
  return (
    <div className="mb-1 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-ink-2">
      <span className="inline-flex items-center gap-1">
        <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: color }} /> So far
      </span>
      <span className="inline-flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-full border-2 border-[var(--text-secondary)]" /> Expected</span>
      <span className="inline-flex items-center gap-1"><span className="inline-block h-2.5 w-5 rounded-sm bg-[var(--band-strong)]" /> Typical miss</span>
      <span className="inline-flex items-center gap-1"><span className="inline-block h-2.5 w-5 rounded-sm border border-dashed border-[var(--text-muted)] bg-[var(--band)]" /> Rough guess</span>
      <span className="inline-flex items-center gap-1"><span className="inline-block h-3 w-0.5 bg-[var(--text-secondary)]" /> Last season</span>
      <span>Middle tick: league middle. Further right is more of it.</span>
    </div>
  )
}

function Numbers({ rows, mixed }: { rows: TeamMetric[]; mixed: boolean }) {
  return (
    <DataTable>
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr>
            <th scope="col" className={th}>Measure</th>
            <th scope="col" className={th}>So far</th>
            <th scope="col" className={th}>Last season</th>
            <th scope="col" className={th}>Read</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => (
            <tr key={m.metric}>
              <td className={td}>{m.label}</td>
              <td className={td}>{m.observed ? `${fmtRate(m.observed.rate, m.unit)} (${ordinal(m.observed.rank)})` : '–'}</td>
              <td className={td}>{m.team_last ? `${fmtRate(m.team_last.rate, m.unit)} (${ordinal(m.team_last.rank)})` : '–'}</td>
              <td className={td}>{VERDICT_TEXT[verdict(m, mixed)]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </DataTable>
  )
}

const SIDES = [['off', 'Offense'], ['def', 'Defense']] as const

/** So far against what was expected, then what the charted measures should look like (ADR 0022). */
export function Tendencies({ file }: { file: TeamFile }) {
  const color = 'var(--team-home)' // set per theme by [data-matchup]
  const starters = starterLines(file)
  return (
    <div data-matchup style={teamDotVars(file.team)} className="flex flex-col gap-6">
      <Legend color={color} />
      {SIDES.map(([side, name]) => {
        const unit = file.units[side]
        const change = callerChange(file, side)
        const rows = sortRows(unit.live, change != null)
        return (
          <Block key={side} title={`${name} so far`} line={change ? changeLine(change, file.through_week) : unitLine(unit)}>
            {side === 'off' && starters.map((s) => <p key={s} className="m-0 text-[13px] text-ink-3">{s} Tendencies may not hold in those games.</p>)}
            <ExpectRow rows={rows.map((m) => toRow(m, file, unit, change != null))} color={color} />
            <Numbers rows={rows} mixed={change != null} />
          </Block>
        )
      })}
      {SIDES.map(([side, name]) => {
        const unit = file.units[side]
        const rows = sortRows(unit.charted)
        const waiting = rows.some((m) => !m.observed)
        return (
          <Block key={side} title={`${name}: what to expect`} line={side === 'off' && waiting ? `These are charted once a year, so ${file.season} isn't in yet. This is the prediction from past seasons.` : undefined}>
            <ExpectRow rows={rows.map((m) => toRow(m, file, unit, false))} color={color} />
            <Numbers rows={rows} mixed={false} />
          </Block>
        )
      })}
      <FinePrint label="How expected works">
        <ul className="list-disc space-y-1.5 pl-5">
          <li>Expected blends the play-caller's own past with the team's last season. The mix is whatever predicted best in past seasons, and it changes with the situation. When a caller moved teams, his past usually predicted better, except on pass rate, where the team's last season did.</li>
          <li>The past seasons run from 2017 for most measures. Motion, play action, RPO, screens, under center and box counts only go back to 2022.</li>
          <li>The band is the typical miss: about 12 to 34 points on a scale of 100, depending on the measure and the situation. About half of all rows land outside it, so outside doesn't mean a shock. These season-long estimates are also being compared with a part-season so far.</li>
          <li>A rough guess means past cases like this one predicted no better, or little better, than picking the league middle. That covers most first-time play-callers and defensive callers who changed teams.</li>
          <li>When a caller changes during a season, the rates mix both, so those rows get no verdict.</li>
          <li>Personnel, coverage, time to throw and pressure come from charting published each spring. Until then those rows are predictions only.</li>
          <li>None of this is good or bad: more motion isn't better than less. It describes what a team does.</li>
        </ul>
      </FinePrint>
    </div>
  )
}
