import { ExpectRow, TipNote, TipRow, TipTitle, type ExpectRowData } from '../../charts'
import { FinePrint } from '../../components/FinePrint'
import { DataTable, td, th } from '../../components/ui'
import type { TeamFile, TeamMetric, TeamUnit } from '../../data/contract'
import { teamDotVars } from '../../lib/teamColors'
import { ordinal } from '../league/helpers'
import { Block } from './Block'
import { VERDICT_TEXT, basis, expectWords, fmtRate, sortRows, starterLines, unitLine, verdict } from './tendencies'

const pct = (v: number) => `${Math.round(100 * Math.min(1, Math.max(0, v)))}%`

function toRow(m: TeamMetric, file: TeamFile, unit: TeamUnit): ExpectRowData {
  const v = verdict(m)
  const e = m.expected
  const o = m.observed
  const [word, than] = expectWords(m)
  const caller = unit.caller?.confirmed ? unit.caller.name : null
  const said = v === 'waiting' ? '' : ` · ${VERDICT_TEXT[v].toLowerCase()}`
  const where = o ? `${fmtRate(o.rate, m.unit)}, ${ordinal(o.rank)} of ${o.of}` : `expected ${word.toLowerCase()} ${than}`
  return {
    key: m.metric,
    label: (
      <>
        {m.label}
        {said && <span className="text-ink-3">{said}</span>}
      </>
    ),
    summary: `${m.label}: ${where}${said.replace(' · ', ', ')}`,
    expected: e?.pct ?? null,
    miss: e?.miss ?? null,
    rough: v === 'rough',
    observed: o?.pct ?? null,
    last: m.team_last?.pct ?? null,
    value: o ? fmtRate(o.rate, m.unit) : word,
    sub: o ? `${ordinal(o.rank)} of ${o.of}` : than,
    ends: m.lo === 'less' ? undefined : [m.lo, m.hi],
    tip: (
      <>
        <TipTitle>{m.label}</TipTitle>
        {o && <TipRow value={`${fmtRate(o.rate, m.unit)}, ${ordinal(o.rank)}`} label="So far" />}
        {e && e.miss != null && <TipRow value={`${pct(e.pct - e.miss)} to ${pct(e.pct + e.miss)}`} label="Expected, share of teams below" />}
        {m.team_last && <TipRow value={`${fmtRate(m.team_last.rate, m.unit)}, ${ordinal(m.team_last.rank)}`} label={`Team in ${m.team_last.season}`} />}
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
      <span className="inline-flex items-center gap-1"><span className="inline-block h-2.5 w-5 rounded-sm bg-[var(--band-strong)]" /> Likely range</span>
      <span className="inline-flex items-center gap-1"><span className="inline-block h-2.5 w-5 rounded-sm border border-dashed border-[var(--text-muted)] bg-[var(--band)]" /> Rough guess</span>
      <span className="inline-flex items-center gap-1"><span className="inline-block h-3 w-0.5 bg-[var(--text-secondary)]" /> Last season</span>
      <span>Middle tick: league middle. Further right is more of it.</span>
    </div>
  )
}

function Numbers({ rows }: { rows: TeamMetric[] }) {
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
              <td className={td}>{VERDICT_TEXT[verdict(m)]}</td>
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
        const rows = sortRows(unit.live)
        return (
          <Block key={side} title={`${name} so far`} line={unitLine(unit)}>
            {side === 'off' && starters.map((s) => <p key={s} className="m-0 text-[13px] text-ink-3">{s} Tendencies may not hold in those games.</p>)}
            <ExpectRow rows={rows.map((m) => toRow(m, file, unit))} color={color} />
            <Numbers rows={rows} />
          </Block>
        )
      })}
      {SIDES.map(([side, name]) => {
        const unit = file.units[side]
        const rows = sortRows(unit.charted)
        return (
          <Block key={side} title={`${name}: what to expect`} line={side === 'off' ? `These are charted once a year, so ${file.season} isn't in yet. This is the prediction from past seasons.` : undefined}>
            <ExpectRow rows={rows.map((m) => toRow(m, file, unit))} color={color} />
            <Numbers rows={rows} />
          </Block>
        )
      })}
      <FinePrint label="How expected works">
        <ul className="list-disc space-y-1.5 pl-5">
          <li>Expected blends the play-caller's own past with the team's last season. The mix comes from what predicted best from 2017 to 2025, and it changes with the situation: a caller who moved teams brings more of his own habits, except pass rate, where the roster matters more.</li>
          <li>The range is the typical miss, and it's wide: about 16 to 25 points on a scale of 100. Inside it reads as expected.</li>
          <li>A rough guess means past cases like this one predicted little better than picking the league middle, so there's no verdict. That covers most first-time play-callers and defensive callers who changed teams.</li>
          <li>Personnel, coverage, time to throw and pressure come from charting published each spring. Until then those rows are predictions only.</li>
          <li>None of this is good or bad: more motion isn't better than less. It describes what a team does.</li>
        </ul>
      </FinePrint>
    </div>
  )
}
