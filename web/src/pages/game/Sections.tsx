import { useState } from 'react'
import { DivergingBars, Dumbbell } from '../../charts'
import { Help } from '../../components/Help'
import { Card, DataTable, ModelBadge, Section, Segmented, TableScroll, td, th } from '../../components/ui'
import type { Game, Meta } from '../../data/contract'
import { fmtUnit, pct, pts, ptsToward, spreadLabel } from '../../lib/format'
import { approachOf, groupOf } from '../../lib/meta'
import { colorVar, SHORT } from '../../lib/models'
import {
  byUnit, contribOrder, contributionItems, dotModels, edgeRows, featureContribRows, injuryRank, sortInjuries, tape, tendencyBlocks,
} from './helpers'

// ----------------------------------------------------------------------- approaches vs market

export function ApproachesVsMarket({ g, meta }: { g: Game; meta: Meta }) {
  const rows = dotModels(g.models)
  const mkt = g.market?.p_home ?? g.models.market_baseline?.p_home ?? null
  const label = (m: string) => SHORT[m] ?? m
  return (
    <Section title="What each approach thinks" help="Each dot is one forecast of the home team's chance of winning. The gray line is the betting market, the benchmark everything is compared with.">
      <p className="mb-3 max-w-3xl text-[13px] text-ink-2">
        Each dot is one forecast of {g.home}'s chance of winning, on a 0 to 100% scale. Color follows the approach; gray is a reference. The gray
        vertical line is the market.
      </p>
      <div className="relative" role="img" aria-label={`Home win chance for ${g.home} by model: ${rows.map((m) => `${label(m)} ${pct(g.models[m].p_home)}`).join(', ')}`}>
        <div className="grid grid-cols-[6.5rem_1fr] items-center gap-y-1 sm:grid-cols-[8rem_1fr]">
          {rows.map((m) => {
            const p = g.models[m].p_home
            const isRef = m === 'market_baseline' || m === 'elo_v0'
            return (
              <div key={m} className="contents">
                <div className="text-[13px]">
                  <Help text={m === 'ensemble' ? 'The average of the four approaches.' : approachOf(meta, m)?.blurb}>
                    <ModelBadge modelId={m} label={label(m)} />
                  </Help>
                </div>
                <div className="relative h-7">
                  <div className="absolute inset-x-0 top-1/2 h-px bg-[var(--border)]" />
                  {[0, 25, 50, 75, 100].map((t) => (
                    <div key={t} className="absolute top-1/2 h-2 w-px -translate-y-1/2 bg-[var(--border)]" style={{ left: `${t}%` }} />
                  ))}
                  {mkt != null && <div className="absolute inset-y-0 w-0.5 -translate-x-1/2 bg-[var(--series-market)] opacity-60" style={{ left: `${100 * mkt}%` }} />}
                  <div
                    className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2"
                    style={{ left: `${100 * p}%`, background: isRef ? 'var(--surface-1)' : colorVar(m), borderColor: colorVar(m) }}
                    title={`${label(m)}: ${g.home} ${pct(p, 1)}`}
                  />
                </div>
              </div>
            )
          })}
          <div />
          <div className="relative h-5 text-[11px] text-ink-3">
            {[0, 25, 50, 75, 100].map((t) => (
              <span key={t} className="absolute -translate-x-1/2" style={{ left: `${t}%` }}>{t}%</span>
            ))}
          </div>
        </div>
        <div className="mt-1 text-center text-[12px] text-ink-3">{g.home} win probability</div>
      </div>
      <DataTable>
        <table className="w-full border-collapse text-[14px]">
          <thead>
            <tr>
              <th className={th}>Model</th>
              <th className={th}>{g.home} win</th>
              <th className={th}>Spread</th>
              <th className={th}>vs market</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((m) => {
              const mp = g.models[m]
              return (
                <tr key={m}>
                  <td className={td}><ModelBadge modelId={m} label={label(m)} /></td>
                  <td className={`${td} tabular`}>{pct(mp.p_home, 1)}</td>
                  <td className={`${td} tabular`}>{spreadLabel(mp.spread_home, g.home, g.away)}</td>
                  <td className={`${td} tabular`}>{m === 'market_baseline' || mp.divergence == null ? '–' : pts(100 * mp.divergence)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </DataTable>
      <p className="mt-2 text-[12px] text-ink-3">Spread is the home spread in points, sportsbook style. "vs market" is the model's home win chance minus the market's, in points.</p>
    </Section>
  )
}

// -------------------------------------------------------------------------------------- why

export function Why({ g, meta }: { g: Game; meta: Meta }) {
  const contrib = g.contributions
  const opts = contribOrder(contrib)
  const [sel, setSel] = useState(opts[0] ?? '')
  if (opts.length === 0) {
    return <Section title="Why they lean the way they do"><p className="text-ink-2">No contribution breakdown for this game.</p></Section>
  }
  const cm = contrib[sel] ?? contrib[opts[0]]
  const items = contributionItems(cm, meta)
  // One scale for every approach so switching tabs doesn't rescale the bars.
  const domain = Math.max(1, ...opts.flatMap((o) => contributionItems(contrib[o], meta).map((i) => Math.abs(i.pp)))) * 1.25
  const groups = Object.keys(cm.groups).sort((a, b) => Math.abs(cm.groups[b].pp ?? 0) - Math.abs(cm.groups[a].pp ?? 0))
  return (
    <Section title="Why they lean the way they do" help="How much each piece of the picture moves the pick, in points of the home team's win chance.">
      <p className="mb-3 max-w-3xl text-[13px] text-ink-2">
        Each bar is how much one piece of the picture moves the pick, in points of {g.home}'s win chance: how far the chance would drop without that
        piece. Right pushes toward {g.home}, left toward {g.away}. The pieces add up only approximately to the total (the effects overlap and the
        final probability is also calibrated).
      </p>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <Segmented label="Approach" value={sel} onChange={setSel} options={opts.map((o) => ({ value: o, label: SHORT[o] ?? o }))} />
        <span className="text-[13px] text-ink-2">
          {SHORT[sel]} says: {g.home} win chance {pct(cm.p_home, 1)}.
        </span>
      </div>
      {approachOf(meta, sel)?.blurb && <p className="mb-2 max-w-3xl text-[13px] text-ink-3">{approachOf(meta, sel)?.blurb}</p>}
      <DivergingBars
        leftLabel={`toward ${g.away}`}
        rightLabel={`toward ${g.home}`}
        domain={domain}
        format={(v) => pts(v)}
        rows={items.map((i) => ({
          key: i.id, label: i.name, value: i.pp,
          title: `${i.name}: ${ptsToward(i.pp, g.home, g.away)}${i.help ? `. ${i.help}` : ''}`,
        }))}
      />
      <h3 className="mt-4 mb-1 text-[15px] font-semibold">Inside each group</h3>
      <div className="flex flex-col gap-1">
        {groups.map((k) => {
          const grp = cm.groups[k]
          const fs = featureContribRows(grp, meta)
          return (
            <details key={k} className="rounded-md border border-line bg-surface-1 px-3 py-1.5">
              <summary className="flex cursor-pointer flex-wrap items-baseline justify-between gap-2">
                <span>
                  <Help text={groupOf(meta, k)?.description}>{groupOf(meta, k)?.name ?? k}</Help>
                </span>
                <span className="tabular text-[13px] text-ink-2">{ptsToward(grp.pp, g.home, g.away)}</span>
              </summary>
              <div className="mt-2">
                {fs.length === 0 ? (
                  <p className="text-[13px] text-ink-3">No feature-level detail.</p>
                ) : (
                  <TableScroll>
                    <table className="w-full border-collapse text-[14px]">
                      <thead>
                        <tr><th className={th}>Feature</th><th className={th}>Push (points of win chance)</th></tr>
                      </thead>
                      <tbody>
                        {fs.map((f) => (
                          <tr key={f.feature}>
                            <td className={td}><Help text={f.help}>{f.label}</Help></td>
                            <td className={`${td} tabular`}>{ptsToward(f.pp, g.home, g.away)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </TableScroll>
                )}
              </div>
            </details>
          )
        })}
      </div>
      <DataTable summary="Where the four approaches differ (all groups side by side)">
        <table className="w-full border-collapse text-[14px]">
          <thead>
            <tr>
              <th className={th}>Group</th>
              {opts.map((o) => <th key={o} className={th}><ModelBadge modelId={o} /></th>)}
            </tr>
          </thead>
          <tbody>
            {['home_field', ...meta.groups.groups.map((x) => x.id).filter((id) => opts.some((o) => id in contrib[o].groups))].map((id) => (
              <tr key={id}>
                <td className={td}>{id === 'home_field' ? 'Home field' : groupOf(meta, id)?.name}</td>
                {opts.map((o) => {
                  const v = id === 'home_field' ? contrib[o].home_field_pp : contrib[o].groups[id]?.pp
                  return <td key={o} className={`${td} tabular`}>{v == null ? '–' : pts(v)}</td>
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </DataTable>
    </Section>
  )
}

// ------------------------------------------------------------------------------ edges + tape

export function Edges({ g, meta }: { g: Game; meta: Meta }) {
  const { rows, none } = edgeRows(g.edges, meta)
  if (rows.length === 0 && none.length === 0) return null
  return (
    <Section
      title="Who has the edge, by group"
      help="A team's edge in a group is how lopsided this matchup is compared with every game since 2005: the 80th percentile means bigger than 80% of matchups."
    >
      <ul className="flex flex-col gap-2">
        {rows.map((r) => (
          <li key={r.id}>
            <div className="text-[14px]">
              <Help text={r.help}>{r.sentence}</Help>
            </div>
            <div className="mt-1 h-1.5 w-full max-w-md rounded bg-surface-2" aria-hidden>
              <div className="h-full rounded" style={{ width: `${r.pct}%`, background: r.favors === g.home ? 'var(--div-pos)' : 'var(--div-neg)' }} />
            </div>
          </li>
        ))}
      </ul>
      {none.length > 0 && <p className="mt-2 text-[13px] text-ink-3">No clear edge: {none.join(', ')}.</p>}
    </Section>
  )
}

export function TaleOfTheTape({ g, meta }: { g: Game; meta: Meta }) {
  const t = tape(g.features, meta)
  const [heading, setHeading] = useState<string>('')
  if (t.length === 0) return <Section title="Tale of the tape"><p className="text-ink-2">No feature values for this game.</p></Section>
  const cur = t.find((x) => x.heading === heading) ?? t[0]
  return (
    <Section title="Tale of the tape" help="The raw numbers behind each group, for each team. Hover any feature or group name for what it means.">
      <div className="mb-3 overflow-x-auto">
        <Segmented label="Group heading" value={cur.heading} onChange={setHeading} options={t.map((x) => ({ value: x.heading, label: x.heading }))} />
      </div>
      <div className="flex flex-col gap-4">
        {cur.groups.map((grp) => (
          <div key={grp.id}>
            <h3 className="mb-1 text-[15px] font-semibold"><Help text={grp.help}>{grp.name}</Help></h3>
            <TableScroll>
              <table className="w-full border-collapse text-[14px]">
                <thead>
                  <tr><th className={th}>Feature</th><th className={th}>{g.away}</th><th className={th}>{g.home}</th></tr>
                </thead>
                <tbody>
                  {grp.rows.map((r) => (
                    <tr key={r.feature}>
                      <td className={td}><Help text={r.help}>{r.label}</Help></td>
                      <td className={`${td} tabular`}>{r.away}</td>
                      <td className={`${td} tabular`}>{r.home}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableScroll>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[12px] text-ink-3">Values that describe the game as a whole (like the market line) show the same number for both teams.</p>
    </Section>
  )
}

// ------------------------------------------------------------------------------- tendencies

export function Tendencies({ g, meta }: { g: Game; meta: Meta }) {
  const sits = Object.entries(meta.tendency_situations)
  const [sit, setSit] = useState(sits[0]?.[0] ?? 'all')
  if (g.tendencies.length === 0) return <Section title="Tendencies"><p className="text-ink-2">No tendency data for this game.</p></Section>
  // meta.json from before the tendency labels were published: say so rather than "not enough plays"
  if (Object.keys(meta.tendency_metrics).length === 0)
    return <Section title="Tendencies"><p className="text-ink-2">Tendency charts return with the next data update.</p></Section>
  const blocks = tendencyBlocks(g.tendencies, meta, sit, g.home, g.away)
  const fmtFor = (unit: string) => (v: number) => fmtUnit(v, unit)
  return (
    <Section
      title="Tendencies: offense vs the other side's defense"
      help="How each offense has played this season next to how the opposing defense has been played against, with the league average for scale."
    >
      <p className="mb-3 max-w-3xl text-[13px] text-ink-2">
        Season-to-date rates, shrunk toward the league average when plays are few. Where the dots are far apart, expect a mismatch. Each chart has
        its own scale.
      </p>
      <div className="mb-4 overflow-x-auto">
        <Segmented label="Situation" value={sit} onChange={setSit} options={sits.map(([value, label]) => ({ value, label }))} />
      </div>
      {blocks.length === 0 && <p className="text-ink-2">Not enough plays yet in this situation.</p>}
      <div className="flex flex-col gap-6">
        {blocks.map((b) => (
          <Card key={b.key}>
            <h3 className="text-[15px] font-semibold">{b.title}</h3>
            <p className="mb-2 text-[12px] text-ink-3">{b.note}</p>
            {byUnit(b.rows).map((u) => (
              <Dumbbell
                key={u.unit}
                aName={b.aName} bName={b.bName} aColor={b.aColor} bColor={b.bColor}
                domain={u.domain}
                format={fmtFor(u.unit)}
                rows={u.rows.map((r) => ({
                  key: r.key, label: r.label, a: r.a, b: r.b, league: r.league,
                  title: `${r.label}: ${b.aName} ${r.a == null ? '–' : fmtUnit(r.a, r.unit)}, ${b.bName} ${r.b == null ? '–' : fmtUnit(r.b, r.unit)}, league ${r.league == null ? '–' : fmtUnit(r.league, r.unit)}. ${r.help}`,
                }))}
              />
            ))}
            <DataTable>
              <table className="w-full border-collapse text-[14px]">
                <thead>
                  <tr><th className={th}>Metric</th><th className={th}>{b.aName}</th><th className={th}>{b.bName}</th><th className={th}>League</th><th className={th}>Plays</th></tr>
                </thead>
                <tbody>
                  {b.rows.map((r) => (
                    <tr key={r.key}>
                      <td className={td}><Help text={r.help}>{r.label}</Help></td>
                      <td className={`${td} tabular`}>{fmtUnit(r.a, r.unit)}</td>
                      <td className={`${td} tabular`}>{fmtUnit(r.b, r.unit)}</td>
                      <td className={`${td} tabular`}>{fmtUnit(r.league, r.unit)}</td>
                      <td className={`${td} tabular`}>{Number.isFinite(r.n) ? r.n : '–'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </DataTable>
          </Card>
        ))}
      </div>
    </Section>
  )
}

// -------------------------------------------------------------------------------- injuries

export function Injuries({ g }: { g: Game }) {
  if (g.injuries.length === 0) return <Section title="Injuries"><p className="text-ink-2">No injury report yet.</p></Section>
  return (
    <Section title="Injuries">
      <div className="grid gap-4 md:grid-cols-2">
        {[g.away, g.home].map((team) => {
          const rows = sortInjuries(g.injuries.filter((i) => i.team === team))
          return (
            <div key={team}>
              <h3 className="mb-1 text-[15px] font-semibold">{team}</h3>
              {rows.length === 0 ? (
                <p className="text-ink-2">None listed.</p>
              ) : (
                <TableScroll>
                  <table className="w-full border-collapse text-[14px]">
                    <thead>
                      <tr><th className={th}>Player</th><th className={th}>Pos</th><th className={th}>Status</th><th className={th}>Injury</th><th className={th}>Practice</th></tr>
                    </thead>
                    <tbody>
                      {rows.map((i) => (
                        <tr key={`${i.player}-${i.status}`}>
                          <td className={td}>{i.player}</td>
                          <td className={td}>{i.pos ?? '–'}</td>
                          <td className={`${td} ${injuryRank(i.status) <= 1 ? 'font-semibold' : ''}`}>{i.status}</td>
                          <td className={td}>{i.injury ?? '–'}</td>
                          <td className={td}>{i.practice ?? '–'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </TableScroll>
              )}
            </div>
          )
        })}
      </div>
    </Section>
  )
}
