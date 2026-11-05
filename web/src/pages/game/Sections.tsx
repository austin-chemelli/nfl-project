import { useState } from 'react'
import { DivergingBars, Dumbbell, MatchupBand, ProbStrip } from '../../charts'
import { Help } from '../../components/Help'
import { Card, DataTable, ModelBadge, Section, Segmented, TableScroll, td, th } from '../../components/ui'
import type { Game, Meta } from '../../data/contract'
import { fmtUnit, pct, pts, ptsFor, ptsSide, ptsToward, spreadLabel } from '../../lib/format'
import { approachOf, groupOf } from '../../lib/meta'
import { SHORT } from '../../lib/models'
import {
  byUnit, contribOrder, contributionItems, dotModels, edgeRows, featureContribRows, injuryRank, sortInjuries, tape, tendencyBlocks,
} from './helpers'

// ----------------------------------------------------------------------- approaches vs market

export function ApproachesVsMarket({ g, meta }: { g: Game; meta: Meta }) {
  const rows = dotModels(g.models)
  const mkt = g.market?.p_home ?? g.models.market_baseline?.p_home ?? null
  const label = (m: string) => SHORT[m] ?? m
  if (rows.length === 0)
    return (
      <Section title="What each approach thinks">
        <p className="text-ink-2">
          No approach forecasts for this game yet: it hasn't been locked or scored. The market{mkt != null ? ` gives ${g.home} ${pct(mkt)}` : ' has no line yet'}.
        </p>
      </Section>
    )
  return (
    <Section title="What each approach thinks" help="Each dot is one forecast of the home team's chance of winning. The gray line is the betting market, the benchmark everything is compared with.">
      <ProbStrip
        home={g.home}
        market={mkt}
        models={rows.filter((m) => m !== 'market_baseline').map((m) => ({ id: m, label: label(m), p: g.models[m].p_home, reference: m === 'elo_v0' }))}
      />
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
              // The market row shows the same line as the chart and the "vs market" column (the game's
              // market snapshot), not the market_baseline model, which can be a few points off.
              const isMkt = m === 'market_baseline' && g.market?.p_home != null
              const mp = isMkt ? { ...g.models[m], p_home: g.market!.p_home!, spread_home: g.market!.spread_home ?? g.models[m].spread_home } : g.models[m]
              return (
                <tr key={m}>
                  <td className={td}>
                    <Help text={approachOf(meta, m)?.blurb}>
                      <ModelBadge modelId={m} label={label(m)} />
                    </Help>
                  </td>
                  <td className={`${td} tabular`}>{pct(mp.p_home, 1)}</td>
                  <td className={`${td} tabular`}>{spreadLabel(mp.spread_home, g.home, g.away)}</td>
                  <td className={`${td} tabular`}>{m === 'market_baseline' || mp.divergence == null ? '–' : pts(100 * mp.divergence)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </DataTable>
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
      <p className="mb-3 max-w-3xl text-[13px] text-ink-2">How far each piece of the picture pushes the pick, in points of {g.home}'s win chance: right toward {g.home}, left toward {g.away}.</p>
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
        format={ptsFor}
        leftColor="var(--team-away)"
        rightColor="var(--team-home)"
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
                  return <td key={o} className={`${td} tabular whitespace-nowrap`}>{v == null ? '–' : ptsSide(v, g.home, g.away)}</td>
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
  const { rows, none } = edgeRows(g.edges, meta, g.neutral_site)
  if (rows.length === 0 && none.length === 0)
    return <Section title="Who has the edge, by group"><p className="text-ink-2">No group edges for this game yet.</p></Section>
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
              <div className="h-full rounded" style={{ width: `${r.pct}%`, background: r.favors === g.home ? 'var(--team-home)' : 'var(--team-away)' }} />
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
  const drawn = cur.groups.flatMap((x) => x.rows).filter((r) => r.band)
  const big = drawn.filter((r) => r.band?.stands).length
  return (
    <Section title="Tale of the tape" help="The raw numbers behind each group, on the league's typical range. Hover any feature or group name for what it means.">
      <div className="mb-3 overflow-x-auto">
        <Segmented label="Group heading" value={cur.heading} onChange={setHeading} options={t.map((x) => ({ value: x.heading, label: x.heading }))} />
      </div>
      {drawn.length > 0 && (
        <>
          <p className="mb-2 max-w-3xl text-[13px] text-ink-2">
            {big === 0 ? `None of these ${drawn.length} gaps stands out` : `${big} of these ${drawn.length} gaps ${big === 1 ? 'stands' : 'stand'} out`}: a gap stands out when it is wider than the middle half of the league.
          </p>
          <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-ink-2">
            <span className="inline-flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-full bg-[var(--team-away)]" /> {g.away}</span>
            <span className="inline-flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-full bg-[var(--team-home)]" /> {g.home}</span>
            <span className="inline-flex items-center gap-1"><span className="inline-flex h-2.5 w-7 overflow-hidden rounded-sm bg-[var(--band)]"><span className="ml-1.5 h-full w-4 bg-[var(--band-strong)]" /></span> Most teams, darker where they bunch up</span>
            <span className="inline-flex items-center gap-1"><span className="inline-block h-3 w-0.5 bg-[var(--text-muted)]" /> Median</span>
            <span>Further right is better</span>
          </div>
        </>
      )}
      <div className="flex flex-col gap-4">
        {cur.groups.map((grp) => {
          const bands = grp.rows.filter((r) => r.band)
          const plain = grp.rows.filter((r) => !r.band)
          return (
            <div key={grp.id}>
              <h3 className="mb-1 text-[15px] font-semibold"><Help text={grp.help}>{grp.name}</Help></h3>
              {bands.length > 0 && (
                <MatchupBand
                  away={g.away} home={g.home}
                  format={(v, key) => fmtUnit(v, bands.find((r) => r.feature === key)?.unit)}
                  rows={bands.map((r) => ({
                    key: r.feature, label: r.label, help: r.help, away: r.band!.awayV, home: r.band!.homeV,
                    lo: r.band!.lo, q1: r.band!.q1, med: r.band!.med, q3: r.band!.q3, hi: r.band!.hi, stands: r.band!.stands, flip: r.band!.flip,
                  }))}
                />
              )}
              {plain.length > 0 && (
                <TableScroll>
                  <table className="w-full border-collapse text-[14px]">
                    <thead>
                      <tr><th className={th}>Feature</th><th className={th}>{g.away}</th><th className={th}>{g.home}</th></tr>
                    </thead>
                    <tbody>
                      {plain.map((r) => (
                        <tr key={r.feature}>
                          <td className={td}><Help text={r.help}>{r.label}</Help></td>
                          <td className={`${td} tabular`}>{r.away}</td>
                          <td className={`${td} tabular`}>{r.home}</td>
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
      <p className="mb-3 max-w-3xl text-[13px] text-ink-2">Where an offense and the defense it faces sit far apart, expect a mismatch.</p>
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
                  key: r.key, label: r.label, a: r.a, b: r.b, league: r.league, help: r.help,
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
