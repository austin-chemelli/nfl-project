import { useId, useState } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card, DataTable, Segmented, TableScroll, td, th } from '../../components/ui'
import { Help } from '../../components/Help'
import type { Coaches } from '../../data/contract'
import { fmtUnit } from '../../lib/format'
import { PercentileBar, Profile } from './Profile'
import { KEY_METRICS, SIDE_NAME, metricsFor, pct0, personLabel, searchPeople, sortedPeople, trendRows, type Person } from './helpers'

const INPUT = 'rounded-md border border-line bg-surface-1 px-2 py-1 text-[13px] text-ink'

export function CoachView({ site, coach, onCoach }: { site: Coaches; coach: string | null; onCoach: (name: string) => void }) {
  const [q, setQ] = useState('')
  const searchId = useId()
  const selectId = useId()
  const people = sortedPeople(site.people)
  const person = people.find((p) => p.name === coach)
  const visible = searchPeople(people, q)
  const options = person && !visible.includes(person) ? [person, ...visible] : visible
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <label htmlFor={searchId} className="flex flex-col gap-1 text-[13px] text-ink-3">
          Search
          <input id={searchId} type="search" className={INPUT} placeholder="Type a name" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <label htmlFor={selectId} className="flex min-w-0 flex-col gap-1 text-[13px] text-ink-3">
          Coordinator or play-caller
          <select id={selectId} className={`${INPUT} max-w-full`} value={person?.name ?? ''} onChange={(e) => onCoach(e.target.value)}>
            <option value="" disabled>Choose a person</option>
            {options.map((p) => <option key={p.name} value={p.name}>{personLabel(p)}</option>)}
          </select>
        </label>
        <span className="text-[13px] text-ink-3">{people.length} people who called plays for a team.</span>
      </div>
      {coach && !person && <p className="text-ink-2">No coach named "{coach}" in the data.</p>}
      {!coach && <p className="text-ink-2">Choose a person to see their seasons.</p>}
      {person && <PersonDetail key={person.name} site={site} person={person} />}
    </div>
  )
}

function PersonDetail({ site, person }: { site: Coaches; person: Person }) {
  const [sideId, setSideId] = useState(person.sides[0]?.side ?? 'off')
  const sd = person.sides.find((s) => s.side === sideId) ?? person.sides[0]
  if (!sd) return <p className="text-ink-2">No seasons on record.</p>
  const side = sd.side
  return (
    <div className="flex flex-col gap-5">
      {person.sides.length > 1 && (
        <Segmented label="Unit" value={side} onChange={setSideId} options={person.sides.map((s) => ({ value: s.side, label: SIDE_NAME[s.side] }))} />
      )}
      <div>
        <h3 className="text-lg font-semibold">{person.name}: {SIDE_NAME[side].toLowerCase()} {sd.role.includes('play') ? 'play-caller' : 'coordinator'}</h3>
        <p className="mt-1">
          {sd.summary ? String(sd.summary.sentence ?? '') : `No seasons before ${site.current_season} with data; only ${site.current_season} so far, which is not a history yet.`}
        </p>
        <p className="mt-1 text-[13px] text-ink-3">
          Stints: {sd.seasons.map((s) => `${s.season} ${s.team}${s.partial ? ' (so far)' : ''}`).join(', ')}.
        </p>
      </div>
      {sd.summary && (
        <Card>
          <Profile summary={sd.summary} metrics={site.metrics} side={side} />
        </Card>
      )}
      <Trend key={side} site={site} sd={sd} side={side} />
      <SeasonTable site={site} sd={sd} side={side} />
    </div>
  )
}

type SideBlock = Person['sides'][number]

function Trend({ site, sd, side }: { site: Coaches; sd: SideBlock; side: 'off' | 'def' }) {
  const options = metricsFor(site.metrics, side)
  const [metric, setMetric] = useState(KEY_METRICS[side][0])
  const m = site.metrics[metric] ?? options[0]?.[1]
  const rows = trendRows(sd.seasons, site.league, side, metric)
  const unit = m?.unit
  const id = useId()
  return (
    <section>
      <h3 className="mb-2 text-base font-semibold">Trend across seasons</h3>
      <label htmlFor={id} className="mb-3 flex w-fit max-w-full flex-col gap-1 text-[13px] text-ink-3">
        Measure
        <select id={id} className={INPUT} value={metric} onChange={(e) => setMetric(e.target.value)}>
          {options.map(([k, d]) => <option key={k} value={k}>{d.label}</option>)}
        </select>
      </label>
      {m && <p className="mb-2 text-[13px] text-ink-2"><Help text={m.help}>{m.label}</Help>: his unit's rate each season against the league that season.</p>}
      <Card>
        <div className="h-64 w-full" role="img" aria-label={`${m?.label ?? 'Measure'} by season, his unit against the league. The numbers are in the table below.`}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="2 3" vertical={false} />
              <XAxis dataKey="label" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} stroke="var(--border)" interval="preserveStartEnd" minTickGap={12} />
              <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 12 }} tickFormatter={(v: number) => fmtUnit(v, unit)} width={56} stroke="var(--border)" domain={['auto', 'auto']} />
              <Tooltip
                contentStyle={{ background: 'var(--surface-1)', border: '1px solid var(--border)', fontSize: 13 }}
                formatter={(v, name) => [typeof v === 'number' ? fmtUnit(v, unit) : '–', name === 'rate' ? 'His unit' : 'League']}
              />
              {unit === 'epa' && <ReferenceLine y={0} stroke="var(--text-muted)" />}
              <Line name="league" type="monotone" dataKey="league" stroke="var(--series-ref)" strokeDasharray="4 3" strokeWidth={2} dot={false} isAnimationActive={false} />
              <Line name="rate" type="monotone" dataKey="rate" stroke="var(--accent)" strokeWidth={2} dot={{ r: 3, fill: 'var(--accent)' }} connectNulls={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-2 text-[13px] text-ink-3">
          Blue = his unit, dashed gray = league average that season; the team after each season marks moves between teams. Coverage measures start in 2018, so older seasons have no man or two-high point. Raw rates are not comparable across the 2023 charting change; read each season against its own league line.
        </p>
        <DataTable>
          <table className="w-full text-[13px]">
            <thead>
              <tr><th className={th}>Season</th><th className={th}>His unit</th><th className={th}>League</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.label}>
                  <td className={td}>{r.label}{r.partial ? ' (so far)' : ''}</td>
                  <td className={`${td} tabular`}>{fmtUnit(r.rate, unit)}</td>
                  <td className={`${td} tabular`}>{fmtUnit(r.league, unit)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </DataTable>
      </Card>
    </section>
  )
}

function SeasonTable({ site, sd, side }: { site: Coaches; sd: SideBlock; side: 'off' | 'def' }) {
  const cols = KEY_METRICS[side].filter((k) => site.metrics[k])
  return (
    <section>
      <h3 className="mb-2 text-base font-semibold">Season by season</h3>
      {side === 'off' && (
        <p className="mb-2 text-[13px] text-ink-3">
          Primary QB = most dropbacks that season for that team. The QB shapes some of these numbers (time to throw, pressure), so read a play-caller's change alongside a QB change.
        </p>
      )}
      <TableScroll>
        <table className="w-full min-w-[40rem] text-[13px]">
          <thead>
            <tr>
              <th className={th}>Season</th>
              <th className={th}>Team</th>
              <th className={th}>Role</th>
              {side === 'off' && <th className={th}>Primary QB</th>}
              {cols.map((k) => <th key={k} className={th}><Help text={site.metrics[k].help}>{site.metrics[k].label}</Help></th>)}
            </tr>
          </thead>
          <tbody>
            {sd.seasons.map((s) => (
              <tr key={`${s.season}-${s.team}`}>
                <td className={`${td} tabular`}>{s.season}{s.partial ? ' (so far)' : ''}</td>
                <td className={td}>{s.team}</td>
                <td className={td}>{s.source === 'play_caller' ? 'play-caller' : 'coordinator'}</td>
                {side === 'off' && <td className={td}>{s.qb ? `${s.qb.name} (${s.qb.dropbacks} dropbacks)` : '–'}</td>}
                {cols.map((k) => {
                  const v = s.metrics[k]
                  const d = site.metrics[k]
                  const league = site.league[String(s.season)]?.[side]?.[k] ?? v?.league
                  return (
                    <td key={k} className={td}>
                      <div className="tabular whitespace-nowrap">{fmtUnit(v?.rate, d.unit)} <span className="text-ink-3">vs {fmtUnit(league, d.unit)}</span></div>
                      <div className="mt-1 flex items-center gap-1.5 whitespace-nowrap">
                        <PercentileBar pct={v?.pct} />
                        <span className="tabular text-ink-3">{pct0(v?.pct)}</span>
                      </div>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </TableScroll>
    </section>
  )
}
