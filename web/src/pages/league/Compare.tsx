import { Dumbbell } from '../../charts'
import type { TeamFeature, TeamsFile } from '../../data/contract'
import { matchupVars } from '../../lib/teamColors'
import { teamInfo } from '../../lib/teams'
import { compareDomain, compareGroups, type CompareRow } from './context'
import { fmtValue, rankText } from './helpers'

const NONE = <></>

/** One measure: its name and both values as text, then the two dots on the league's range. */
function Row({ row, a, b, file }: { row: CompareRow; a: string; b: string; file: TeamsFile }) {
  const f: TeamFeature = row.feature
  const side = (code: string, v: number | null) => `${code} ${fmtValue(v, f)}${rankText(file.teams[code], f) ? ` (${rankText(file.teams[code], f)})` : ''}`
  return (
    <li className="border-b border-line py-2">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 text-[13px]">
        <span className="font-medium text-ink">{f.short}</span>
        {f.better === 'lower' && <span className="text-[12px] text-ink-3">lower is better</span>}
      </div>
      <div className="tabular flex flex-wrap gap-x-3 text-[12px] text-ink-2">
        <span>{side(a, row.a)}</span>
        <span>{side(b, row.b)}</span>
        {row.edge && <span className="text-ink-3">Edge: {row.edge === 'a' ? a : b}</span>}
      </div>
      <div className="-mb-2 -mt-3">
      <Dumbbell
        rows={[{ key: f.id, label: f.short, a: row.a, b: row.b, league: f.mean, help: f.description }]}
        aName={teamInfo(a).name}
        bName={teamInfo(b).name}
        aColor="var(--team-away)"
        bColor="var(--team-home)"
        format={(v) => fmtValue(v, f)}
        domain={compareDomain(row)}
        labelWidth={0}
        legend={NONE}
      />
      </div>
    </li>
  )
}

/**
 * Two teams on every published measure (ADR 0019), one dumbbell per measure on the league's range, in
 * the registry's groups. A group is a disclosure and the first is open, so 45 rows stay short on a phone.
 */
export function Compare({ file, a, b, onClose }: { file: TeamsFile; a: string; b: string; onClose: () => void }) {
  const groups = compareGroups(file, a, b)
  const an = teamInfo(a).name
  const bn = teamInfo(b).name
  return (
    <section aria-label={`${an} compared with ${bn}`} data-matchup style={matchupVars(a, b)} className="mt-4 rounded-lg border border-line bg-surface-1 p-3 text-[13px]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-[15px] font-medium text-ink">
            {an} and {bn}
          </h3>
          <p className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-ink-2">
            <span className="inline-flex items-center gap-1">
              <span aria-hidden className="inline-block size-2.5 rounded-full" style={{ background: 'var(--team-away)' }} />
              {a}
            </span>
            <span className="inline-flex items-center gap-1">
              <span aria-hidden className="inline-block size-2.5 rounded-full" style={{ background: 'var(--team-home)' }} />
              {b}
            </span>
            <span className="inline-flex items-center gap-1">
              <span aria-hidden className="inline-block h-3 w-0.5 bg-[var(--text-muted)]" /> League average
            </span>
          </p>
          <p className="mt-1 text-[12px] text-ink-3">Each line spans the league's range for that measure. Where a measure has a good direction, better is to the right.</p>
        </div>
        <button type="button" onClick={onClose} aria-label="Stop comparing" className="shrink-0 rounded px-2 py-1 text-ink-2 hover:text-ink">
          ✕
        </button>
      </div>
      {groups.length === 0 && <p className="mt-2 text-ink-2">Neither team has a value on these measures yet.</p>}
      <div className="mt-2 flex flex-col">
        {groups.map((g, i) => (
          <details key={g.name} open={i === 0} className="group border-t border-line">
            <summary className="flex cursor-pointer flex-wrap items-baseline justify-between gap-x-3 py-2 text-ink hover:text-ink">
              <span className="font-medium">{g.name}</span>
              <span className="tabular text-[12px] text-ink-3">
                {g.rows.length} measures{g.aAhead + g.bAhead > 0 ? ` · ${a} ahead on ${g.aAhead}, ${b} on ${g.bAhead}` : ''}
              </span>
            </summary>
            <ul className="m-0 list-none p-0">
              {g.rows.map((r) => (
                <Row key={r.feature.id} row={r} a={a} b={b} file={file} />
              ))}
            </ul>
          </details>
        ))}
      </div>
    </section>
  )
}
