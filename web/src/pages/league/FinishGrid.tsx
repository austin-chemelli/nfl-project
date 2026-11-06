import { TipTitle, useChartTip } from '../../charts/ChartTip'
import { useWidth } from '../../charts/useWidth'
import type { SimilarNeighbour } from '../../data/contract'
import { finishGrid, levelCounts, type Level } from './similar'

const CELL = 30
const GAP = 4

/** A level's fill: a one-hue ramp from missed to champion that changes in lightness, so it reads without hue. */
const levelFill = (l: Level) => `var(--finish-${l})`

/**
 * How the nearest seasons finished: one square each, furthest round first, darker (lighter in the dark theme)
 * the further they went. The legend prints the counts, and each square names its season on hover or focus.
 */
export function FinishGrid({ nearest, active, onActive }: { nearest: SimilarNeighbour[]; active: number | null; onActive: (i: number | null) => void }) {
  const [ref, width] = useWidth()
  const { box, bind, card, at } = useChartTip()
  const cells = finishGrid(nearest)
  const cols = Math.max(1, Math.min(cells.length, Math.floor((width + GAP) / (CELL + GAP))))
  const rows = Math.ceil(cells.length / cols)
  const h = rows * (CELL + GAP) - GAP + 4
  const counts = levelCounts(cells)
  const hovered = cells.find((c) => `${c.index}` === at?.key)
  return (
    <div ref={ref} className="w-full">
      <div ref={box} className="relative">
        <svg width={width} height={h} role="group" aria-label={`How the ${cells.length} nearest seasons finished, furthest round first`} className="block">
          {cells.map((c, i) => {
            const b = bind(`${c.index}`)
            const x = (i % cols) * (CELL + GAP) + 2
            const y = Math.floor(i / cols) * (CELL + GAP) + 2
            const on = active === c.index
            return (
              <g
                key={c.index}
                {...b}
                role="img"
                aria-label={c.label}
                onPointerMove={(e) => { b.onPointerMove(e); onActive(c.index) }}
                onPointerLeave={() => { b.onPointerLeave(); onActive(null) }}
                onFocus={(e) => { b.onFocus(e); onActive(c.index) }}
                onBlur={() => { b.onBlur(); onActive(null) }}
                className="finish-cell"
              >
                <rect x={x} y={y} width={CELL} height={CELL} rx={4} fill={levelFill(c.level)} stroke={on ? 'var(--text-primary)' : c.level === 0 ? 'var(--band-strong)' : 'var(--surface-1)'} strokeWidth={on ? 2.5 : 1.5} />
                {c.level >= 4 && <path d={c.level === 5 ? `M${x + 8} ${y + 16} l5 5 l9 -11` : `M${x + 9} ${y + 15} h12`} fill="none" stroke="var(--surface-1)" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />}
              </g>
            )
          })}
        </svg>
        {card(hovered && <TipTitle note={`Nearest seasons are listed from ${hovered.index + 1} of ${cells.length}`}>{hovered.label}</TipTitle>)}
      </div>
      <ul aria-label="Finishes and how many seasons" className="m-0 mt-2 flex list-none flex-wrap gap-x-4 gap-y-1 p-0 text-[12px] text-ink-2">
        {counts.map((c) => (
          <li key={c.level} className="inline-flex items-center gap-1.5">
            <span aria-hidden className="inline-block size-3 rounded-[3px]" style={{ background: levelFill(c.level), boxShadow: `inset 0 0 0 1px ${c.level === 0 ? 'var(--band-strong)' : 'transparent'}` }} />
            <span className="tabular font-medium text-ink">{c.count}</span> {c.label}
          </li>
        ))}
      </ul>
    </div>
  )
}
