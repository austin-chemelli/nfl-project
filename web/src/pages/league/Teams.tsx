import { useSearchParams } from 'react-router'
import { Scatter } from '../../charts/Scatter'
import { TipNote, TipRow, TipTitle } from '../../charts/ChartTip'
import { FinePrint } from '../../components/FinePrint'
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

function AxisSelect({ label, value, features, onChange }: { label: string; value: string; features: TeamFeature[]; onChange: (id: string) => void }) {
  return (
    <label className="flex min-w-0 flex-col gap-0.5 text-[12px] text-ink-3">
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)} className={`${field} max-w-full`}>
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
    </label>
  )
}

/** The Teams tab: every team on any two measures (ADR 0019). */
export function Teams({ file }: { file: TeamsFile }) {
  const [params, setParams] = useSearchParams()
  const update = (fn: (p: URLSearchParams) => void) =>
    setParams((prev) => { const n = new URLSearchParams(prev); fn(n); return n }, { replace: true })

  const axes = resolveAxes(file, params.get('x'), params.get('y'))
  if (!axes) return <p className="text-ink-2">Team charts appear after the next data update.</p>
  const { x, y } = axes

  const mode = colorMode(params.get('color'))
  const divisions = divisionsOf(file)
  const div = params.get('div') && divisions.includes(params.get('div')!) ? params.get('div')! : null
  const team = params.get('team') && params.get('team')! in file.teams ? params.get('team')! : null
  const { points, missing } = buildPoints(file, x, y, mode, div)
  const features = usableFeatures(file)
  const through = file.week - 1

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
        <TipNote>Through Week {through} · tap for games</TipNote>
      </>
    )
  }

  const rows = Object.keys(file.teams).sort()
  const rk = (code: string, f: TeamFeature) => file.teams[code].rank?.[f.id]

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <p className="text-ink-2">Every team on any two measures, season to date entering Week {file.week}.</p>

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
        <AxisSelect label="X axis" value={x.id} features={features} onChange={(id) => setAxes(id, y.id)} />
        <AxisSelect label="Y axis" value={y.id} features={features} onChange={(id) => setAxes(x.id, id)} />
        <button type="button" onClick={() => setAxes(y.id, x.id)} aria-label="Swap axes" className={`${field} px-3`}>
          ⇄
        </button>
        <div className="flex flex-col gap-0.5 text-[12px] text-ink-3">
          Color
          <Segmented<ColorMode>
            label="Color"
            value={mode}
            onChange={(m) => update((n) => { if (m === 'conference') n.delete('color'); else n.set('color', m); if (m !== 'division') n.delete('div') })}
            options={[{ value: 'conference', label: 'Conference' }, { value: 'division', label: 'Division' }, { value: 'none', label: 'None' }]}
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

      {team && <Panel code={team} team={file.teams[team]} week={file.week} onClose={() => update((n) => n.delete('team'))} />}

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
        <p>Season to date: each team's numbers entering its next game, so early weeks lean on last season. Scheme priors are coordinator history, not this year's tape.</p>
        <p>Values update after the Tuesday refresh. The corner labels describe where a team sits; they don't judge it.</p>
      </FinePrint>
    </div>
  )
}
