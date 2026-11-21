import { pct } from '../../lib/format'

/**
 * Win chance on a 0-100% track: the filled part is the market's chance, the dot is the Student's.
 * The two labels sit under the ends, so the picture reads before the numbers do.
 */
export function ChanceBar({ market, student }: { market: number; student: number }) {
  const m = Math.max(0, Math.min(1, market)) * 100
  const s = Math.max(0, Math.min(1, student)) * 100
  const label = `Market ${pct(market)}, Student ${pct(student)}`
  return (
    <div>
      <div role="img" aria-label={label} className="relative h-4">
        <div className="absolute inset-x-0 top-1/2 h-2 -translate-y-1/2 overflow-hidden rounded-full bg-[var(--band)]">
          <div className="h-full rounded-full bg-[var(--series-market)] transition-[width] duration-[var(--dur-slow)]" style={{ width: `${m}%` }} />
        </div>
        <span
          aria-hidden="true"
          className="absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface-1 bg-[var(--series-student)] shadow transition-[left] duration-[var(--dur-slow)]"
          style={{ left: `${s}%` }}
        />
      </div>
      <div aria-hidden="true" className="tabular mt-1 flex justify-between text-[12px] text-ink-3">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-[var(--series-market)]" />
          Market {pct(market)}
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-[var(--series-student)]" />
          Student {pct(student)}
        </span>
      </div>
    </div>
  )
}
