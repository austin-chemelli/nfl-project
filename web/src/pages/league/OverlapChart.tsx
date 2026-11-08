import { TipNote, TipRow, TipTitle, useChartTip } from '../../charts/ChartTip'
import { useWidth } from '../../charts/useWidth'
import type { SimilarFile, SimilarNeighbour, SimilarTeam } from '../../data/contract'
import { teamDotVars } from '../../lib/teamColors'
import { finishLevel, laneOffsets, overlapSummary, rowSpread, seasonLabel, spreadText } from './similar'

const PAD = 12
const ROW = 66
const LANE = 6
const MAX_LANE = 2

type Pt = { x: number; y: number }

/** One neighbour's mark: hollow circle if it missed, filled circle if it made the playoffs, diamond if it reached the conference championship game or beyond. */
function Mark({ n, x, y, r }: { n: SimilarNeighbour; x: number; y: number; r: number }) {
  const lvl = finishLevel(n)
  if (lvl >= 3) {
    const d = r * 1.45
    return <path d={`M${x} ${y - d} L${x + d} ${y} L${x} ${y + d} L${x - d} ${y} Z`} fill="var(--finish-5)" stroke="var(--surface-1)" strokeWidth={1} />
  }
  if (lvl >= 1) return <circle cx={x} cy={y} r={r} fill="var(--finish-3)" stroke="var(--surface-1)" strokeWidth={1} />
  return <circle cx={x} cy={y} r={r - 0.5} fill="var(--surface-1)" stroke="var(--text-muted)" strokeWidth={1.5} />
}

/**
 * Where the overlap is: one strip per measure (0 to 100 among teams at this many games), this team as one
 * large dot in its color and its nearest seasons as small dots by finish. A faint band marks the middle
 * half of those seasons; a row is tight when they sit close to this team, however narrow the band. The active season (hovered or focused here, in the
 * list or in the grid) rings its seven dots and joins them with a line.
 */
export function OverlapChart({ code, name, entry, measures, active, onActive }: {
  code: string
  name: string
  entry: SimilarTeam
  measures: SimilarFile['measures']
  active: number | null
  onActive: (i: number | null) => void
}) {
  const [ref, width] = useWidth()
  const { box, bind, card, at } = useChartTip()
  const x0 = PAD
  const x1 = width - PAD
  const sx = (p: number) => x0 + (Math.max(0, Math.min(100, p)) / 100) * (x1 - x0)
  const axis = 18
  const h = measures.length * ROW + axis
  const near = entry.nearest

  const rows = measures.map((m, mi) => {
    const top = mi * ROW
    const cy = top + 43
    const vals = near.map((n) => n.profile[mi])
    const xs = vals.map((v) => (v == null ? NaN : sx(v)))
    const lanes = laneOffsets(xs.map((x) => (Number.isNaN(x) ? -1e9 : x)), 8)
    const ys = lanes.map((l) => cy + Math.max(-MAX_LANE, Math.min(MAX_LANE, l)) * LANE)
    const spread = rowSpread(vals.filter((v): v is number => v != null), entry.profile[mi])
    return { m, mi, top, cy, xs, ys, spread, mine: entry.profile[mi] }
  })

  // The hovered mark's key is `${neighbour}:${measure}` ('team:<measure>' for the large dot).
  const [hn, hm] = (at?.key ?? '').split(':')
  const hoverN = hn && hn !== 'team' ? near[Number(hn)] : undefined
  const hoverM = hm != null ? rows[Number(hm)] : undefined

  const line: Pt[] = active == null ? [] : rows.filter((r) => !Number.isNaN(r.xs[active])).map((r) => ({ x: r.xs[active], y: r.ys[active] }))
  const dim = active != null

  return (
    <div ref={ref} className="w-full">
      <div ref={box} className="relative" data-matchup style={teamDotVars(code)}>
        <svg width={width} height={h} role="img" aria-label={overlapSummary(entry, measures, name)} className="block text-[12px]">
          {rows.map((r) => (
            <g key={r.m.id} data-row={r.m.id}>
              <text x={x0} y={r.top + 14} className="fill-[var(--text-secondary)] text-[12.5px] font-medium">
                {r.m.label}
                {r.m.id.endsWith('sos') && <tspan className="fill-[var(--text-muted)] font-normal"> (right = hardest)</tspan>}
              </text>
              {r.spread && (
                <text x={x1} y={r.top + 14} textAnchor="end" className="fill-[var(--text-muted)] text-[11px]">
                  {width >= 480 ? (r.spread.tight === 'tight' ? 'tight · ' : r.spread.tight === 'loose' ? 'loose · ' : '') : ''}
                  {spreadText(r.spread)}
                </text>
              )}
              <line x1={x0} x2={x1} y1={r.cy} y2={r.cy} stroke="var(--border)" strokeWidth={1} />
              <line x1={sx(50)} x2={sx(50)} y1={r.cy - 18} y2={r.cy + 18} stroke="var(--border)" strokeWidth={1} strokeDasharray="2 3" />
              {r.spread && <rect x={sx(r.spread.lo)} y={r.cy - 19} width={Math.max(2, sx(r.spread.hi) - sx(r.spread.lo))} height={38} rx={5} fill="var(--band-strong)" opacity={0.4} />}
              {near.map((n, i) => {
                if (Number.isNaN(r.xs[i])) return null
                const b = bind(`${i}:${r.mi}`)
                return (
                  <g
                    key={i}
                    {...b}
                    tabIndex={-1}
                    aria-hidden
                    onPointerMove={(e) => { b.onPointerMove(e); onActive(i) }}
                    onPointerLeave={() => { b.onPointerLeave(); onActive(null) }}
                    style={{ ...b.style, opacity: dim && i !== active ? 0.45 : 1, transition: 'opacity var(--dur-base) var(--ease-out)' }}
                  >
                    <circle cx={r.xs[i]} cy={r.ys[i]} r={7} fill="transparent" />
                    <Mark n={n} x={r.xs[i]} y={r.ys[i]} r={4} />
                  </g>
                )
              })}
            </g>
          ))}
          {line.length > 1 && <polyline points={line.map((p) => `${p.x},${p.y}`).join(' ')} fill="none" stroke="var(--text-primary)" strokeWidth={1.25} strokeLinejoin="round" opacity={0.7} />}
          {active != null &&
            rows.map((r) =>
              Number.isNaN(r.xs[active]) ? null : (
                <g key={r.m.id} aria-hidden pointerEvents="none">
                  <circle cx={r.xs[active]} cy={r.ys[active]} r={9} fill="var(--surface-1)" stroke="var(--text-primary)" strokeWidth={1.75} />
                  <Mark n={near[active]} x={r.xs[active]} y={r.ys[active]} r={4.5} />
                </g>
              ),
            )}
          {rows.map((r) => {
            if (r.mine == null) return null
            const b = bind(`team:${r.mi}`)
            return (
              <g key={r.m.id} {...b} tabIndex={-1} aria-hidden>
                <circle cx={sx(r.mine)} cy={r.cy} r={8} fill="var(--team-home)" stroke="var(--team-away)" strokeWidth={2.5} />
                <circle cx={sx(r.mine)} cy={r.cy} r={12} fill="transparent" />
              </g>
            )
          })}
          {[0, 50, 100].map((t) => (
            <text key={t} x={sx(t)} y={h - 4} textAnchor={t === 0 ? 'start' : t === 100 ? 'end' : 'middle'} className="fill-[var(--text-muted)] text-[11px]">
              {t}
            </text>
          ))}
        </svg>
        {card(
          hoverM && (
            <>
              <TipTitle note={hn === 'team' ? undefined : `${name}: ${hoverM.mine == null ? 'no value' : Math.round(hoverM.mine)}`}>
                {hn === 'team' ? name : hoverN ? seasonLabel(hoverN) : ''}
              </TipTitle>
              <TipRow value={hn === 'team' ? (hoverM.mine == null ? '–' : Math.round(hoverM.mine)) : hoverN?.profile[hoverM.mi] == null ? '–' : Math.round(hoverN.profile[hoverM.mi])} label={`${hoverM.m.label}, 0 to 100`} />
              {hoverM.spread && <TipNote>Middle half of the nearest seasons: {Math.round(hoverM.spread.lo)} to {Math.round(hoverM.spread.hi)}</TipNote>}
            </>
          ),
        )}
      </div>
    </div>
  )
}

/** The key under the chart, and the line that names the active season. */
export function OverlapKey({ code, name, active, near }: { code: string; name: string; active: number | null; near: SimilarNeighbour[] }) {
  const n = active == null ? undefined : near[active]
  return (
    <div data-matchup style={teamDotVars(code)} className="mt-1 text-[12px] text-ink-2">
      <p className="m-0 flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="inline-flex items-center gap-1.5">
          <svg width="16" height="16" aria-hidden><circle cx="8" cy="8" r="6.5" fill="var(--team-home)" stroke="var(--team-away)" strokeWidth="2" /></svg>
          {name}
        </span>
        <span className="text-ink-3">{near.length} nearest seasons:</span>
        <span className="inline-flex items-center gap-1.5">
          <svg width="14" height="14" aria-hidden><circle cx="7" cy="7" r="3" fill="var(--surface-1)" stroke="var(--text-muted)" strokeWidth="1.5" /></svg>
          missed
        </span>
        <span className="inline-flex items-center gap-1.5">
          <svg width="14" height="14" aria-hidden><circle cx="7" cy="7" r="3.5" fill="var(--finish-3)" /></svg>
          made the playoffs
        </span>
        <span className="inline-flex items-center gap-1.5">
          <svg width="14" height="14" aria-hidden><path d="M7 1.5 L12.5 7 L7 12.5 L1.5 7 Z" fill="var(--finish-5)" /></svg>
          reached the conference championship game or beyond
        </span>
        <span className="inline-flex items-center gap-1.5">
          <svg width="16" height="12" aria-hidden><rect x="1" y="1" width="14" height="10" rx="3" fill="var(--band-strong)" opacity="0.4" /></svg>
          middle half of them
        </span>
      </p>
      <p aria-live="polite" className="mb-0 mt-1.5 min-h-[2.4em] text-ink-3">
        {n ? <span className="text-ink">{seasonLabel(n)}</span> : 'Hover a season to trace it.'}
      </p>
    </div>
  )
}
