import { hasSpark, sparkLabel, type SparkPoint } from './context'

const W = 64
const H = 22
const PAD = 3

/**
 * A team's chance of the playoffs by week as a small line (ADR 0019). Drawn only from two points; with
 * fewer it renders nothing, so no empty box or gap is left. The scale is the series' own range, at least
 * 20 points tall, so a flat team reads flat. Static: no animation.
 */
export function Spark({ points }: { points: SparkPoint[] }) {
  if (!hasSpark(points)) return null
  const vals = points.map((p) => p.value)
  let lo = Math.min(...vals)
  let hi = Math.max(...vals)
  if (hi - lo < 0.2) {
    const mid = (hi + lo) / 2
    lo = mid - 0.1
    hi = mid + 0.1
  }
  const x = (i: number) => PAD + (i * (W - 2 * PAD)) / (points.length - 1)
  const y = (v: number) => H - PAD - ((v - lo) / (hi - lo)) * (H - 2 * PAD)
  const line = points.map((p, i) => `${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ')
  const last = points.length - 1
  return (
    <svg role="img" aria-label={sparkLabel(points)} viewBox={`0 0 ${W} ${H}`} width={W} height={H} className="spark block shrink-0">
      <polyline points={line} fill="none" stroke="var(--team-home)" strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={x(last)} cy={y(points[last].value)} r={2.2} fill="var(--team-home)" />
    </svg>
  )
}
