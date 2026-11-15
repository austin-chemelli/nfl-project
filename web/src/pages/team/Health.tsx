/**
 * How far the team is from full strength (M24.7): the share of its full-strength lineup expected on
 * the field this week, by position room, the lineup on the field (key players starred, who is out
 * and who steps in), the scored claims' sentences, and the same share for every game so far with an
 * outlook that brings players back when eligible. Shares are in spot weights, not player values
 * (round 3): every starter at a position counts the same, a key player 1.5 times. Context only
 * (ADR 0027).
 */
import { scaleLinear } from 'd3-scale'
import { TipRow, TipTitle, useChartTip } from '../../charts/ChartTip'
import { DepthField, DepthFieldKey } from '../../charts/DepthField'
import { useWidth } from '../../charts/useWidth'
import { FinePrint } from '../../components/FinePrint'
import type { TeamFile, TeamHealth } from '../../data/contract'
import { outLine, roomsLede } from '../../lib/health'
import { Block } from './Block'
import { Rooms } from './Rooms'

const pct = (v: number | null | undefined) => (v == null ? '–' : `${Math.round(100 * v)}%`)
const name = (s: { player: string; key: boolean }) => (s.key ? `${s.player} ★` : s.player)

const H = 170
const PAD = { top: 14, right: 16, bottom: 26, left: 40 }

type Pt = { week: number; health: number; out: number; keyOut: number; kind: 'past' | 'now' | 'outlook' }

/** Health by week: the games so far solid, this week marked, the outlook dashed. */
export function HealthChart({ health }: { health: TeamHealth }) {
  const [ref, width] = useWidth()
  const { box, at, bind, card } = useChartTip()
  const pts_: Pt[] = [
    ...health.by_week.filter((w) => w.health != null).map((w) => ({ week: w.week, health: w.health!, out: w.out, keyOut: w.key_out, kind: 'past' as const })),
    ...(health.now.health != null ? [{ week: health.now.week, health: health.now.health, out: health.now.out, keyOut: health.now.key_out, kind: 'now' as const }] : []),
    ...health.outlook.filter((w) => w.health != null).map((w) => ({ week: w.week, health: w.health!, out: w.out, keyOut: w.key_out, kind: 'outlook' as const })),
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
          <TipRow value={hovered.out} label={outLine(hovered.out, hovered.keyOut).replace(/^\d+ /, '')} />
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
    ? 'No depth chart yet.'
    : h.out > 0
      ? `At ${pct(h.health)} of full strength going into Week ${h.week}: ${outLine(h.out, h.key_out)}.`
      : `At full strength going into Week ${h.week}: every full-strength starter is available.`
  const doubtNames = h.starters.filter((s) => s.doubt).map(name)
  const listed = file.availability?.reported ? file.availability.listed : []
  const back = health.outlook.find((o) => o.health != null && o.health >= 0.995)
  return (
    <div className="flex flex-col gap-8">
      <Block title="Full-strength lineup" line="The best lineup the chart has had this season, as it stands this week: who is out, and who steps in. Hover a player for his return window and the chart behind him.">
        <div className="flex flex-col gap-3" data-testid="health-depth">
          <DepthField starters={h.starters} week={h.week} />
          <DepthFieldKey />
        </div>
      </Block>
      <Block title={`Health, Week ${h.week}`} line={health.rooms.length > 0 && h.health != null ? `${lede} ${roomsLede(health.rooms)}` : lede}>
        {!h.reported && (
          <p className="m-0 text-[13px] text-ink-3" data-testid="health-doubt">
            No game statuses yet this week (teams post them Friday), so the share counts only reserve lists.
            {doubtNames.length > 0
              ? <> In doubt from practice: {doubtNames.join(', ')} (marked under their rooms).</>
              : ' No full-strength starter missed practice.'}
          </p>
        )}
        <Rooms rooms={health.rooms} h={h} />
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
        <p>Full strength is the team&apos;s best lineup this season: at each spot, the best player the depth chart has had as the starter since March who is still on the roster and is out now (a healthy player the chart moved down lost the job; he doesn&apos;t count). The share weighs each spot by its position (a quarterback more than a guard, every corner the same) and a key player (★) one and a half times: the top 30% at his position across the league by our player ratings, a veteran paid like the top 15% at his position, or a 1st-round pick on his rookie deal. The ratings only pick the key players; we don&apos;t show them, because they aren&apos;t reliable enough player by player. A player on IR may return after missing four of his team&apos;s games; IR from before Week 1 usually means the season, so it gets no window. Questionable and Doubtful count by how often players with that status have played since 2016. Before Friday&apos;s statuses, a starter who missed or was limited in practice is shown as in doubt but not counted: a Wednesday absence is often a rest day. A position room&apos;s rank is against the other 31 teams&apos; rooms. Every room but the offensive line is graded on its full-strength starters&apos; own numbers, wherever they played, this season and last (last season counting half, small samples pulled toward the league average), so a starter back from injury counts: EPA and success rate for the offense; pressures, sacks and tackles per snap, missed tackles, and yards and completions allowed per target for the defense. The offensive line has no per-player blocking stats, so it is graded on team stats (pressure and sack rates allowed, yards before contact) from the games it went into at 80% strength or more. The rank now is an estimate: the share of the room that is missing pulls its grade toward a room of backups. Context only: no prediction uses it.</p>
      </FinePrint>
    </div>
  )
}
