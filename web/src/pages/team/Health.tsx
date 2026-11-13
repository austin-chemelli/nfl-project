/**
 * How far the team is from full strength (M24.7): the share of its full-strength starters' value
 * expected on the field this week, by position group, a depth chart of each spot (the full-strength
 * starter, his status and window, who is behind him), the scored claims' sentences, and
 * the same share for every game so far with an outlook that brings players back when eligible.
 * Context only (ADR 0027).
 */
import { scaleLinear } from 'd3-scale'
import { TipRow, TipTitle, useChartTip } from '../../charts/ChartTip'
import { useWidth } from '../../charts/useWidth'
import { FinePrint } from '../../components/FinePrint'
import { TableScroll, td, th } from '../../components/ui'
import type { HealthStarter, TeamFile, TeamHealth } from '../../data/contract'
import { Block } from './Block'

const GROUP: Record<string, string> = {
  QB: 'Quarterback', RB: 'Running back', WR: 'Receivers', TE: 'Tight end', OL: 'Offensive line',
  EDGE: 'Edge rushers', DL: 'Interior line', LB: 'Linebackers', CB: 'Cornerbacks', S: 'Safeties',
}
const pct = (v: number | null | undefined) => (v == null ? '–' : `${Math.round(100 * v)}%`)
const pts = (v: number) => v.toFixed(1)

/** "IR since Wk 9 · eligible Wk 13", "Out", "IR since camp · no return window". */
// oxlint-disable-next-line react/only-export-components
export function whenBack(s: HealthStarter, week: number): string {
  if (!s.reserve) return s.status ?? ''
  const since = s.since_week == null ? '' : s.since_week <= 1 ? ' since camp' : ` since Wk ${s.since_week}`
  if (s.eligible_week == null) return `${s.status}${since} · no return window`
  if (s.eligible_week <= week) return `${s.status}${since} · eligible now`
  return `${s.status}${since} · eligible Wk ${s.eligible_week}`
}

function Groups({ h }: { h: TeamHealth['now'] }) {
  const outBy = (grp: string) => h.starters.filter((s) => s.grp === grp && (s.missing_pts ?? 0) > 0).map((s) => s.player)
  const doubtBy = (grp: string) => h.starters.filter((s) => s.grp === grp && s.doubt).map((s) => s.player)
  return (
    <ul className="m-0 flex list-none flex-col gap-2.5 p-0" data-testid="health-groups">
      {h.groups.map((g) => {
        const share = g.health ?? 1
        const out = outBy(g.grp)
        const doubt = doubtBy(g.grp)
        const doubtShare = g.full_pts ? Math.min(share, g.doubt_pts / g.full_pts) : 0
        return (
          <li key={g.grp} className="grid grid-cols-[minmax(0,7.5rem)_minmax(0,1fr)_3rem] items-center gap-x-3 gap-y-0.5 text-[14px]">
            <span className="truncate text-ink-2">{GROUP[g.grp] ?? g.grp}</span>
            <span className="relative h-3 overflow-hidden rounded-full bg-[var(--surface-2)] ring-1 ring-[var(--border)]" role="img" aria-label={`${GROUP[g.grp] ?? g.grp} at ${pct(share)} of full strength`}>
              <span className="absolute inset-y-0 left-0 rounded-full bg-[var(--accent)]" style={{ width: `${Math.max(0, Math.min(1, share)) * 100}%` }} />
              {doubtShare > 0 && (
                <span data-doubt className="absolute inset-y-0" style={{ left: `${(share - doubtShare) * 100}%`, width: `${doubtShare * 100}%`, background: 'repeating-linear-gradient(135deg, var(--accent) 0 3px, var(--surface-2) 3px 6px)' }} />
              )}
            </span>
            <span className={`tabular text-right ${share < 1 ? 'font-medium text-ink' : 'text-ink-3'}`}>{pct(share)}</span>
            {(out.length > 0 || doubt.length > 0) && (
              <span className="col-start-2 col-end-4 text-[12px] text-ink-3">
                {out.length > 0 && <>missing {out.join(', ')} · {pts(g.missing_pts)} of {pts(g.full_pts)} pts</>}
                {out.length > 0 && doubt.length > 0 && '; '}
                {doubt.length > 0 && <>in doubt (practice) {doubt.join(', ')}</>}
              </span>
            )}
          </li>
        )
      })}
    </ul>
  )
}

const tone = (s: { status: string | null; p_play?: number; doubt?: boolean }) =>
  s.status == null ? '' : s.doubt || (s.p_play ?? 1) >= 0.5 ? 'text-ink-2 italic' : 'text-[var(--critical)]'

function DepthRows({ rows, week }: { rows: HealthStarter[]; week: number }) {
  return (
    <TableScroll>
      <table className="w-full table-fixed border-collapse text-[14px]">
        <colgroup><col className="w-12" /><col /><col /></colgroup>
        <thead>
          <tr>
            <th className={th}>Spot</th>
            <th className={th}>Full strength</th>
            <th className={th}>Behind him on the chart</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => {
            const out = (s.missing_pts ?? 0) > 0
            return (
              <tr key={s.slot} data-slot={s.slot} className={out ? 'bg-[var(--surface-2)]' : ''}>
                <td className={`${td} text-ink-3`}>{s.slot.replace(/[123]$/, '')}</td>
                <td className={`${td} break-words`}>
                  <span className="font-medium text-ink">{s.player}</span>
                  {s.value_pts != null && <span className="tabular text-ink-3"> · {pts(s.value_pts)}</span>}
                  {s.status && <span className={`block text-[13px] ${tone(s)}`}>{whenBack(s, week)}{!s.reserve && !s.doubt && s.status !== 'Out' ? ` · plays ${pct(s.p_play)}` : ''}</span>}
                </td>
                <td className={`${td} break-words text-ink-2`}>
                  {s.depth.length === 0 && (s.replaced_by ? <span>{s.replaced_by}</span> : <span className="text-ink-3">–</span>)}
                  {s.depth.map((d, i) => (
                    <span key={d.player} className={i === 0 && out ? 'font-medium text-ink' : ''}>
                      {i > 0 && <span className="text-ink-3">, then </span>}
                      {d.player}
                      {d.value_pts != null && <span className="tabular text-ink-3"> · {pts(d.value_pts)}</span>}
                      {d.status && <span className={`text-[13px] ${tone(d)}`}> ({d.status})</span>}
                    </span>
                  ))}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </TableScroll>
  )
}

function DepthChart({ h }: { h: TeamHealth['now'] }) {
  return (
    <div className="flex flex-col gap-5" data-testid="health-depth">
      {(['offense', 'defense'] as const).map((u) => {
        const rows = h.starters.filter((s) => s.unit === u)
        return rows.length > 0 && (
          <div key={u} className="flex flex-col gap-1">
            <h4 className="m-0 text-[13px] font-medium uppercase tracking-wide text-ink-3">{u === 'offense' ? 'Offense' : 'Defense'}</h4>
            <DepthRows rows={rows} week={h.week} />
          </div>
        )
      })}
    </div>
  )
}

const H = 170
const PAD = { top: 14, right: 16, bottom: 26, left: 40 }

type Pt = { week: number; health: number; missing: number; kind: 'past' | 'now' | 'outlook' }

/** Health by week: the games so far solid, this week marked, the outlook dashed. */
export function HealthChart({ health }: { health: TeamHealth }) {
  const [ref, width] = useWidth()
  const { box, at, bind, card } = useChartTip()
  const pts_: Pt[] = [
    ...health.by_week.filter((w) => w.health != null).map((w) => ({ week: w.week, health: w.health!, missing: w.missing_pts, kind: 'past' as const })),
    ...(health.now.health != null ? [{ week: health.now.week, health: health.now.health, missing: health.now.missing_pts, kind: 'now' as const }] : []),
    ...health.outlook.filter((w) => w.health != null).map((w) => ({ week: w.week, health: w.health!, missing: w.missing_pts, kind: 'outlook' as const })),
  ]
  if (pts_.length < 2) return null
  const weeks = pts_.map((p) => p.week)
  const lo = Math.min(0.5, Math.floor(Math.min(...pts_.map((p) => p.health)) * 10) / 10)
  const x = scaleLinear().domain([Math.min(...weeks), Math.max(...weeks)]).range([PAD.left, width - PAD.right])
  const y = scaleLinear().domain([lo, 1]).range([H - PAD.bottom, PAD.top])
  const line = (ps: Pt[]) => ps.map((p, i) => `${i ? 'L' : 'M'}${x(p.week)},${y(p.health)}`).join('')
  const solid = pts_.filter((p) => p.kind !== 'outlook')
  const dashed = pts_.filter((p) => p.kind !== 'past')
  const ticks = [lo, (lo + 1) / 2, 1]
  const hovered = pts_.find((p) => `w${p.week}` === at?.key)
  return (
    <div ref={box} className="relative">
      <div ref={ref}>
        <svg width={width} height={H} role="img" aria-label="Share of full strength by week" data-testid="health-chart">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--border)" />
              <text x={PAD.left - 6} y={y(t) + 4} textAnchor="end" fontSize={11} fill="var(--text-muted)">{pct(t)}</text>
            </g>
          ))}
          {weeks.map((w) => (
            <text key={w} x={x(w)} y={H - 8} textAnchor="middle" fontSize={11} fill="var(--text-muted)">{w}</text>
          ))}
          <path d={line(solid)} fill="none" stroke="var(--accent)" strokeWidth={2} />
          {dashed.length > 1 && <path d={line(dashed)} fill="none" stroke="var(--accent)" strokeWidth={2} strokeDasharray="4 4" opacity={0.7} />}
          {pts_.map((p) => (
            <g key={p.week} {...bind(`w${p.week}`)} data-kind={p.kind}>
              <circle cx={x(p.week)} cy={y(p.health)} r={10} fill="transparent" />
              <circle cx={x(p.week)} cy={y(p.health)} r={p.kind === 'now' ? 5 : 3} fill={p.kind === 'outlook' ? 'var(--surface-1)' : 'var(--accent)'} stroke="var(--accent)" strokeWidth={1.5} />
            </g>
          ))}
          {health.now.health != null && (
            <text x={x(health.now.week)} y={y(health.now.health) - 9} textAnchor="middle" fontSize={11} fontWeight={600} fill="var(--text-primary)">{pct(health.now.health)}</text>
          )}
        </svg>
      </div>
      {hovered && card(
        <>
          <TipTitle note={hovered.kind === 'outlook' ? 'if players return when eligible' : hovered.kind === 'now' ? 'this week' : 'going into the game'}>Week {hovered.week}</TipTitle>
          <TipRow value={pct(hovered.health)} label="of full strength" />
          <TipRow value={`${pts(hovered.missing)} pts`} label="missing" />
        </>,
      )}
    </div>
  )
}

export function Health({ file }: { file: TeamFile }) {
  const health = file.health
  if (!health) return null
  const h = health.now
  const lede = h.health == null
    ? 'No starter values yet.'
    : h.missing_pts > 0
      ? `At ${pct(h.health)} of full strength going into Week ${h.week}: ${pts(h.missing_pts)} of ${pts(h.full_pts)} points of starter value expected to miss.`
      : `At full strength going into Week ${h.week}: every full-strength starter is available.`
  const doubtNames = h.starters.filter((s) => s.doubt).map((s) => s.player)
  const listed = file.availability?.reported ? file.availability.listed : []
  const back = health.outlook.find((o) => o.health != null && o.health >= 0.995)
  return (
    <div className="flex flex-col gap-8">
      <Block title={`Health, Week ${h.week}`} line={lede}>
        {!h.reported && (
          <p className="m-0 text-[13px] text-ink-3" data-testid="health-doubt">
            No game statuses yet this week (teams post them Friday), so the share counts only reserve lists.
            {doubtNames.length > 0
              ? <> In doubt from practice: {doubtNames.join(', ')} ({pts(h.doubt_pts)} pts, striped in the bars).</>
              : ' No full-strength starter missed practice.'}
          </p>
        )}
        <Groups h={h} />
      </Block>
      <Block title="Depth chart" line="Each spot's full-strength starter, this week's status, and who is behind him on the latest chart (in bold where he plays instead).">
        <DepthChart h={h} />
      </Block>
      {listed.length > 0 && (
        <Block title="What we said about this week">
          <ul className="m-0 flex list-none flex-col gap-2 p-0" data-testid="health-claims">
            {listed.map((k) => (
              <li key={`${k.player}-${k.grp}`} className="border-b border-line pb-2 text-ink">{k.sentence}</li>
            ))}
          </ul>
        </Block>
      )}
      <Block
        title="By week"
        line={back && h.health != null && h.health < 0.995
          ? `Back to full strength by Week ${back.week} if everyone returns when eligible.`
          : 'Each game so far, this week, and the next weeks if players return when eligible (dashed).'}
      >
        <HealthChart health={health} />
      </Block>
      <FinePrint>
        <p>Full strength is the team&apos;s best lineup this season: at each spot, the most valuable player the depth chart has had as the starter since March who is still on the roster and is out now (a healthy player the chart moved down lost the job; he doesn&apos;t count). Each is valued as he was going into his last game. A player on IR may return after missing four of his team&apos;s games; IR from before Week 1 usually means the season, so it gets no window. Questionable and Doubtful count by how often players with that status have played since 2016. Before Friday's statuses, a starter who missed or was limited in practice is shown as in doubt but not counted: a Wednesday absence is often a rest day, and the play rates we can measure (23% after a missed last practice, 74% after a limited one) are for the week's last practice. Context only: no prediction uses it.</p>
      </FinePrint>
    </div>
  )
}
