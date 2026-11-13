/** A what-if change in points of probability: "▲23" / "▼8", nothing under a point (M26.4). */
import { fmtProb } from './playoffs'

/** Below this change (probability) a what-if cell shows no arrow. */
const MOVE_MIN = 0.01

export function Move({ from, to, big = false }: { from: number; to: number; big?: boolean }) {
  const d = to - from
  if (Math.abs(d) < MOVE_MIN) return big ? <span aria-hidden className="w-9 shrink-0" /> : null
  const up = d > 0
  return (
    <span
      title={`${fmtProb(from)} now`}
      aria-label={`${up ? 'up' : 'down'} from ${fmtProb(from)}`}
      className={`tabular shrink-0 text-[11px] font-semibold ${big ? 'w-9 text-left' : 'ml-1'}`}
      style={{ color: up ? 'var(--good)' : 'var(--critical)' }}
    >
      {up ? '▲' : '▼'}
      {Math.round(Math.abs(d) * 100)}
    </span>
  )
}

