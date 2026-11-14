/**
 * A team's full-strength lineup on the field (M24.7 round 3): offense and defense in their base
 * formations, one ring per spot. A key player's ring carries a star; a starter who won't play is an
 * empty dashed ring with a badge (IR, O, D, Q) and the man who steps in named under it; a practice
 * doubt before Friday is striped. Every ring is the same size: no per-player values on show. Hover a
 * ring for his status, return window and the chart behind him. On a phone the same lineup reads as
 * room cards. The color is the team's (`--team-home`/`--team-away` under `[data-matchup]`) or the
 * accent on the team page.
 */
import { useId } from 'react'
import type { HealthStarter } from '../data/contract'
import { GROUP, GROUP_ORDER, badge, lastName, stepsIn, tone, whenBack } from '../lib/health'
import { TipNote, TipRow, TipTitle, useChartTip } from './ChartTip'

const W = 640
const H = 232
const LOS = 22
const R = 13

// Spot -> (x, y), both units facing the line at the top.
const SPOTS: Record<string, [number, number]> = {
  WR1: [44, 52], WR3: [124, 112], LT: [200, 52], LG: [260, 52], C: [320, 52], RG: [380, 52], RT: [440, 52],
  TE: [506, 52], WR2: [596, 52], QB: [320, 128], RB: [320, 192],
  LCB: [44, 60], WLB: [140, 108], LDE: [200, 52], LDT: [280, 52], NT: [320, 52], RDT: [360, 52],
  RDE: [440, 52], SLB: [500, 108], LILB: [262, 132], MLB: [320, 132], RILB: [378, 132], RCB: [596, 60],
  SS: [236, 196], FS: [404, 196],
}

const BADGE_FILL: Record<string, string> = { IR: 'var(--critical)', PUP: 'var(--critical)', RES: 'var(--critical)', O: 'var(--critical)', INA: 'var(--critical)', D: 'var(--critical)', Q: 'var(--warning)', '?': 'var(--warning)' }
const BADGE_INK: Record<string, string> = { Q: '#1b1f24', '?': '#1b1f24' }

function Star({ x, y, r, fill, stroke }: { x: number; y: number; r: number; fill: string; stroke?: string }) {
  const pts = Array.from({ length: 10 }, (_, i) => {
    const a = (Math.PI / 5) * i - Math.PI / 2
    const rr = i % 2 ? r * 0.45 : r
    return `${x + rr * Math.cos(a)},${y + rr * Math.sin(a)}`
  }).join(' ')
  return <polygon points={pts} fill={fill} stroke={stroke} strokeWidth={stroke ? 1.25 : undefined} strokeLinejoin="round" />
}

function Ring({ s, color, stripe, bind }: { s: HealthStarter; color: string; stripe: string; bind: ReturnType<typeof useChartTip>['bind'] }) {
  const xy = SPOTS[s.slot]
  if (!xy) return null
  const [x, y] = xy
  const t = tone(s)
  const b = badge(s)
  const sub = t === 'out' || t === 'iffy' ? stepsIn(s) : null
  const bw = b && b.length > 1 ? 9 + 5 * b.length : 14
  return (
    <g {...bind(s.slot)} data-slot={s.slot} data-tone={t} data-key={s.key || undefined} aria-label={label(s)}>
      <circle cx={x} cy={y} r={R + 8} fill="transparent" />
      {t === 'out' ? (
        <circle cx={x} cy={y} r={R} fill="var(--surface-1)" stroke={color} strokeWidth={1.75} strokeDasharray="3 2.5" />
      ) : (
        <circle cx={x} cy={y} r={R} fill={t === 'doubt' ? `url(#${stripe})` : color} fillOpacity={t === 'iffy' ? 0.45 : 1} stroke={color} strokeWidth={1.75} />
      )}
      {s.key && <Star x={x} y={y} r={7} fill={t === 'out' || t === 'doubt' ? color : 'var(--surface-1)'} stroke={t === 'doubt' ? 'var(--surface-1)' : undefined} />}
      {b && (
        <g data-badge={b}>
          <rect x={x + R * 0.55} y={y - R - 6} width={bw} height={13} rx={6.5} fill={BADGE_FILL[b] ?? 'var(--critical)'} stroke="var(--surface-1)" strokeWidth={1.5} />
          <text x={x + R * 0.55 + bw / 2} y={y - R + 3.8} textAnchor="middle" fontSize={9} fontWeight={700} fill={BADGE_INK[b] ?? '#fff'}>{b}</text>
        </g>
      )}
      <text x={x} y={y + R + 13} textAnchor="middle" fontSize={11.5} fontWeight={s.key ? 650 : 400} fill={t === 'out' ? 'var(--text-muted)' : 'var(--text-primary)'} textDecoration={t === 'out' ? 'line-through' : undefined}>
        {lastName(s.player)}
      </text>
      {sub && (
        <text x={x} y={y + R + 26} textAnchor="middle" fontSize={10.5} fill="var(--text-secondary)">→ {lastName(sub)}</text>
      )}
    </g>
  )
}

function label(s: HealthStarter) {
  return `${s.slot}: ${s.player}${s.key ? ', key player' : ''}${s.status ? `, ${s.status}` : ''}${stepsIn(s) && s.status ? `; ${stepsIn(s)} steps in` : ''}`
}

function Tip({ s, week }: { s: HealthStarter; week: number }) {
  const t = tone(s)
  return (
    <>
      <TipTitle note={`${s.slot.replace(/[123]$/, '')}${s.grp ? ` · ${GROUP[s.grp] ?? s.grp}` : ''}`}>{s.player}{s.key ? ' ★' : ''}</TipTitle>
      {s.key && <TipNote>Key player: among the best at his position.</TipNote>}
      {s.status ? <TipRow value={whenBack(s, week)} label="" /> : <TipNote>Not on a reserve list or this week&apos;s report.</TipNote>}
      {t === 'iffy' && <TipRow value={`${Math.round(100 * s.p_play)}%`} label={`of players listed ${s.status} have played`} />}
      {t === 'doubt' && <TipNote>Hurt in practice; no game status until Friday.</TipNote>}
      {s.depth.length > 0 && <TipRow value={s.depth.map((d) => d.player + (d.status ? ` (${d.status})` : '')).join(', then ')} label="behind him" />}
      {s.depth.length === 0 && s.replaced_by && <TipRow value={s.replaced_by} label="playing instead" />}
    </>
  )
}

function Unit({ title, spots, color, week }: { title: string; spots: HealthStarter[]; color: string; week: number }) {
  const { box, at, bind, card } = useChartTip()
  const stripe = useId().replace(/:/g, '')
  const hovered = spots.find((s) => s.slot === at?.key)
  return (
    <figure className="m-0 min-w-0">
      <figcaption className="mb-1 text-[12px] font-medium uppercase tracking-wide text-ink-3">{title}</figcaption>
      <div ref={box} className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="group" aria-label={`${title}: full-strength starters`}>
          <defs>
            <pattern id={stripe} width={5} height={5} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width={5} height={5} fill="var(--surface-1)" />
              <rect width={2.5} height={5} fill={color} />
            </pattern>
          </defs>
          <rect x={0} y={0} width={W} height={H} rx={8} fill="var(--surface-2)" />
          <line x1={8} x2={W - 8} y1={LOS} y2={LOS} stroke="var(--text-muted)" strokeWidth={1} strokeDasharray="5 4" />
          {spots.map((s) => <Ring key={s.slot} s={s} color={color} stripe={stripe} bind={bind} />)}
        </svg>
        {hovered && card(<Tip s={hovered} week={week} />)}
      </div>
    </figure>
  )
}

/** The phone layout: one card per position room. */
function Rooms({ starters, week }: { starters: HealthStarter[]; week: number }) {
  const groups = GROUP_ORDER.filter((g) => starters.some((s) => s.grp === g))
  return (
    <div className="grid gap-2">
      {groups.map((g) => {
        const rows = starters.filter((s) => s.grp === g)
        const out = rows.filter((s) => tone(s) !== 'in').length
        return (
          <section key={g} className="rounded-md border border-line bg-[var(--surface-1)] px-3 py-2" data-room={g}>
            <h5 className="m-0 flex justify-between text-[13px] font-medium text-ink-2">
              <span>{GROUP[g] ?? g}</span>
              {out > 0 && <span className="text-ink-3">{out} of {rows.length} out or in doubt</span>}
            </h5>
            <ul className="m-0 mt-1 flex list-none flex-col gap-1 p-0 text-[14px]">
              {rows.map((s) => {
                const t = tone(s)
                const sub = t === 'out' || t === 'iffy' ? stepsIn(s) : null
                return (
                  <li key={s.slot} data-slot={s.slot}>
                    <span className="inline-block w-10 text-ink-3">{s.slot.replace(/[123]$/, '')}</span>
                    <span className={`${s.key ? 'font-semibold' : ''} ${t === 'out' ? 'text-ink-3 line-through' : 'text-ink'}`}>{s.player}{s.key ? ' ★' : ''}</span>
                    {s.status && <span className={`block pl-10 text-[13px] ${t === 'out' ? 'text-[var(--critical)]' : 'text-ink-2 italic'}`}>{whenBack(s, week)}{sub ? ` → ${sub}` : ''}</span>}
                  </li>
                )
              })}
            </ul>
          </section>
        )
      })}
    </div>
  )
}

export function DepthField({ starters, week, color = 'var(--accent)', testId = 'depth-field' }: { starters: HealthStarter[]; week: number; color?: string; testId?: string }) {
  const units = (['offense', 'defense'] as const).map((u) => [u, starters.filter((s) => s.unit === u)] as const).filter(([, rows]) => rows.length > 0)
  return (
    <div data-testid={testId}>
      <div className="hidden max-w-[760px] gap-4 sm:grid">
        {units.map(([u, rows]) => <Unit key={u} title={u === 'offense' ? 'Offense' : 'Defense'} spots={rows} color={color} week={week} />)}
      </div>
      <div className="sm:hidden">
        <Rooms starters={starters} week={week} />
      </div>
    </div>
  )
}

/** The key under the field, once per page. */
export function DepthFieldKey({ color = 'var(--accent)' }: { color?: string }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-ink-3">
      <span className="inline-flex items-center gap-1.5">
        <svg width={16} height={16} aria-hidden><circle cx={8} cy={8} r={7} fill={color} /><Star x={8} y={8} r={4.5} fill="var(--surface-1)" /></svg>
        key player
      </span>
      <span className="inline-flex items-center gap-1.5">
        <svg width={16} height={16} aria-hidden><circle cx={8} cy={8} r={6.5} fill="var(--surface-1)" stroke={color} strokeWidth={1.5} strokeDasharray="3 2.5" /></svg>
        out (IR, O), with who steps in
      </span>
      <span className="inline-flex items-center gap-1.5">
        <svg width={16} height={16} aria-hidden><circle cx={8} cy={8} r={6.5} fill={color} fillOpacity={0.45} stroke={color} strokeWidth={1.5} /></svg>
        Questionable or Doubtful
      </span>
      <span>? hurt in practice, no game status yet</span>
    </div>
  )
}
