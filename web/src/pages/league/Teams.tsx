import { useEffect, useId, useRef } from 'react'
import { useSearchParams } from 'react-router'
import { Scatter } from '../../charts/Scatter'
import { TipNote, TipRow, TipTitle } from '../../charts/ChartTip'
import { FinePrint } from '../../components/FinePrint'
import { Help } from '../../components/Help'
import { DataTable, Segmented, td, th } from '../../components/ui'
import type { TeamFeature, TeamsFile } from '../../data/contract'
import { dash } from '../../lib/format'
import { teamInfo } from '../../lib/teams'
import {
  availablePresets,
  buildPoints,
  colorMode,
  divisionsOf,
  fmtValue,
  groupFeatures,
  quadrantsFor,
  rankText,
  recordText,
  resolveAxes,
  usableFeatures,
  type ColorMode,
} from './helpers'
import { Panel } from './Panel'

const field = 'rounded-md border border-line bg-surface-1 px-2 py-1 text-[13px] text-ink'

function AxisSelect({ label, value, features, help, onChange }: { label: string; value: string; features: TeamFeature[]; help: string; onChange: (id: string) => void }) {
  const id = useId()
  return (
    <div className="flex min-w-0 flex-col gap-0.5 text-[12px] text-ink-3">
      <span>
        <label htmlFor={id}>{label}</label> <Help text={help} />
      </span>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} className={`${field} max-w-full`}>
        {groupFeatures(features).map((g) => (
          <optgroup key={g.name} label={g.name}>
            {g.features.map((f) => (
              <option key={f.id} value={f.id}>
                {f.short}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </div>
  )
}

/** The Teams tab: every team on any two measures (ADR 0019). */
export function Teams({ file }: { file: TeamsFile }) {
  const [params, setParams] = useSearchParams()
  const update = (fn: (p: URLSearchParams) => void) =>
    setParams((prev) => { const n = new URLSearchParams(prev); fn(n); return n }, { replace: true })

  const raw = params.get('team')
  // hasOwn, not `in`: ?team=constructor is on every object's prototype
  const team = raw && Object.hasOwn(file.teams, raw) ? raw : null

  // Bring the panel into view when a team is picked; a shared link keeps its place at the top.
  const panel = useRef<HTMLElement>(null)
  const picker = useRef<HTMLSelectElement>(null)
  const shown = useRef(team)
  useEffect(() => {
    if (team && team !== shown.current) {
      panel.current?.scrollIntoView?.({ block: 'nearest' })
      panel.current?.focus({ preventScroll: true })
    }
    shown.current = team
  }, [team])

  const axes = resolveAxes(file, params.get('x'), params.get('y'))
  if (!axes) return <p className="text-ink-2">Team charts appear after the next data update.</p>
  const { x, y } = axes

  const mode = colorMode(params.get('color'))
  const divisions = divisionsOf(file)
  const div = params.get('div') && divisions.includes(params.get('div')!) ? params.get('div')! : null
  const { points, missing } = buildPoints(file, x, y, mode, div)
  const rows = Object.keys(file.teams).sort((a, b) => teamInfo(a).name.localeCompare(teamInfo(b).name))
  const features = usableFeatures(file)

  const setAxes = (nx: string, ny: string) => update((n) => { n.set('x', nx); n.set('y', ny) })
  const axis = (f: TeamFeature) => ({ title: f.short, flip: f.better === 'lower', mean: f.mean, format: (v: number) => fmtValue(v, f), better: f.better != null })

  const tip = (key: string) => {
    const t = file.teams[key]
    if (!t) return null
    return (
      <>
        <TipTitle note={`${t.division} · ${recordText(t)}`}>{teamInfo(key).name}</TipTitle>
        {[x, y].map((f) => (
          <TipRow key={f.id} value={fmtValue(t.values[f.id], f)} label={[f.short, rankText(t, f)].filter(Boolean).join(' · ')} />
        ))}
        <TipNote>{t.through_week != null ? `Through Week ${t.through_week} · ` : ''}tap for games</TipNote>
      </>
    )
  }

  const rk = (code: string, f: TeamFeature) => file.teams[code].rank?.[f.id]

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <p className="text-ink-2">Every team on any two measures, entering its next game.</p>

      <div role="group" aria-label="Starting views" className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:px-0">
        {availablePresets(file).map((p) => {
          const on = p.x === x.id && p.y === y.id
          return (
            <button
              key={p.id}
              type="button"
              aria-pressed={on}
              onClick={() => setAxes(p.x, p.y)}
              className={`shrink-0 whitespace-nowrap rounded-full border px-3 py-1 text-[13px] ${on ? 'border-[var(--accent)] bg-accent/20 font-medium text-ink' : 'border-line text-ink-2 hover:text-ink'}`}
            >
              {p.chip}
            </button>
          )
        })}
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex min-w-0 flex-col gap-0.5 text-[12px] text-ink-3">
          Find a team
          <select
            ref={picker}
            value={team ?? ''}
            onChange={(e) => update((n) => { if (e.target.value) n.set('team', e.target.value); else n.delete('team') })}
            className={`${field} max-w-full`}
          >
            <option value="">All teams</option>
            {rows.map((c) => (
              <option key={c} value={c}>
                {teamInfo(c).name}
              </option>
            ))}
          </select>
        </label>
        <AxisSelect label="X axis" value={x.id} help={x.description} features={features.filter((f) => f.id !== y.id)} onChange={(id) => setAxes(id, y.id)} />
        <AxisSelect label="Y axis" value={y.id} help={y.description} features={features.filter((f) => f.id !== x.id)} onChange={(id) => setAxes(x.id, id)} />
        <button type="button" onClick={() => setAxes(y.id, x.id)} aria-label="Swap axes" className={`${field} px-3`}>
          ⇄
        </button>
        <div className="flex flex-col gap-0.5 text-[12px] text-ink-3">
          Color
          <Segmented<ColorMode>
            label="Color"
            value={mode}
            onChange={(m) => update((n) => { if (m === 'team') n.delete('color'); else n.set('color', m); if (m !== 'division') n.delete('div') })}
            options={[{ value: 'team', label: 'Team' }, { value: 'conference', label: 'Conference' }, { value: 'division', label: 'Division' }, { value: 'none', label: 'None' }]}
          />
        </div>
      </div>

      {mode === 'division' && (
        <div role="group" aria-label="Division" className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:px-0">
          {divisions.map((d) => (
            <button
              key={d}
              type="button"
              aria-pressed={d === div}
              onClick={() => update((n) => { if (d === div) n.delete('div'); else n.set('div', d) })}
              className={`shrink-0 whitespace-nowrap rounded-full border px-3 py-1 text-[13px] ${d === div ? 'border-[var(--accent)] bg-accent/20 font-medium text-ink' : 'border-line text-ink-2 hover:text-ink'}`}
            >
              {d}
            </button>
          ))}
        </div>
      )}
      {mode === 'conference' && (
        <p className="flex gap-4 text-[12px] text-ink-2">
          <span><span aria-hidden className="mr-1 inline-block size-2 rounded-full" style={{ background: 'var(--conf-afc)' }} />AFC</span>
          <span><span aria-hidden className="mr-1 inline-block size-2 rounded-full" style={{ background: 'var(--conf-nfc)' }} />NFC</span>
        </p>
      )}

      <Scatter
        label={`Teams by ${x.short} and ${y.short}`}
        points={points}
        x={axis(x)}
        y={axis(y)}
        quadrants={quadrantsFor(x, y)}
        selected={team}
        onSelect={(k) => update((n) => n.set('team', k))}
        tip={tip}
      />
      {missing.length > 0 && <p className="text-[13px] text-ink-3">Not shown: {missing.join(', ')} (no value yet on one of these measures).</p>}

      {team && <Panel ref={panel} code={team} team={file.teams[team]} onClose={() => { update((n) => n.delete('team')); picker.current?.focus() }} />}

      <DataTable>
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr>
              <th className={th}>Team</th>
              <th className={`${th} text-right`}>{x.short}</th>
              <th className={`${th} text-right`}>Rank</th>
              <th className={`${th} text-right`}>{y.short}</th>
              <th className={`${th} text-right`}>Rank</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c}>
                <td className={td}>{teamInfo(c).name}</td>
                <td className={`${td} tabular text-right`}>{fmtValue(file.teams[c].values[x.id], x)}</td>
                <td className={`${td} tabular text-right`}>{rk(c, x) ?? dash}</td>
                <td className={`${td} tabular text-right`}>{fmtValue(file.teams[c].values[y.id], y)}</td>
                <td className={`${td} tabular text-right`}>{rk(c, y) ?? dash}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataTable>

      <FinePrint>
        <p>Each team's numbers as they stand entering its next game, so early weeks lean on last season. Form measures cover recent games, and a streak can run across seasons. Measures marked "vs avg" are the play-caller's past seasons against the league average, not this year's tape.</p>
        <p>Numbers update with Tuesday's refresh and each lock, so a game played since then isn't in them yet. Once a team's season ends they stop before its last game. The corner labels only describe where a team sits on these two measures.</p>
      </FinePrint>
    </div>
  )
}
