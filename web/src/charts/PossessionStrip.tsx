/**
 * Who had the ball, on `WpChart`'s time axis (ADR 0020): one segment per drive in the offense's color,
 * running to the next drive's start, with a tick where a drive scored. Segments take hover and tap but
 * no tab stop: `DriveField` below it carries the same drives for the keyboard.
 */
import type { Drive } from '../data/contract'
import { TipNote, TipRow, TipTitle, useChartTip } from './ChartTip'
import { useWidth } from './useWidth'
import { timeScale } from './wpScale'

export type DriveTip = { title: string; result: string; detail: string | null; span: string | null }

const TICK = 7
const BAND = 10
const HEIGHT = TICK + BAND

const SCORES = new Set(['Touchdown', 'Field goal', 'Opp touchdown', 'Safety'])
// oxlint-disable-next-line react/only-export-components
export const isScore = (d: Drive) => d.result != null && SCORES.has(d.result)

export function PossessionStrip({ drives, endT, home, describe }: {
  drives: Drive[]
  endT: number
  home: string
  describe: (d: Drive) => DriveTip
}) {
  const [ref, width] = useWidth()
  const { box, at, bind, card } = useChartTip()
  const x = timeScale(width, endT)
  const color = (d: Drive) => `var(--team-${d.team === home ? 'home' : 'away'})`
  const segments = drives.map((d, i) => ({ d, x0: x(d.t0), x1: x(drives[i + 1]?.t0 ?? endT) }))
  const active = drives.find((d) => String(d.n) === at?.key)
  const tip = active ? describe(active) : null
  const counts = [...new Set(drives.map((d) => d.team))].map((t) => `${t} ${drives.filter((d) => d.team === t).length}`).join(', ')
  return (
    <div ref={ref} className="w-full">
      <div ref={box} className="relative">
        <svg width={width} height={HEIGHT} className="block">
          <g role="img" aria-label={`Possession by drive: ${counts}`}>
            {segments.map(({ d, x0, x1 }) => (
              <rect key={d.n} data-testid="drive-segment" x={x0} y={TICK} width={Math.max(1, x1 - x0 - 1)} height={BAND} fill={color(d)} opacity={!active || active === d ? 1 : 0.55} />
            ))}
            {drives.filter(isScore).map((d) => (
              <line key={d.n} data-testid="drive-score" x1={x(d.t1)} x2={x(d.t1)} y1={0} y2={TICK + BAND} stroke="var(--text-primary)" strokeWidth={1.5} />
            ))}
          </g>
          <g>
            {segments.map(({ d, x0, x1 }) => (
              <g key={d.n} {...bind(String(d.n))} tabIndex={-1}>
                <rect x={x0} y={0} width={Math.max(1, x1 - x0)} height={HEIGHT} fill="transparent" />
              </g>
            ))}
          </g>
        </svg>
        {card(tip && (
          <>
            <TipTitle>{tip.title}</TipTitle>
            <TipRow color={active ? color(active) : undefined} value={tip.result} label={tip.span ?? ''} />
            {tip.detail && <TipNote>{tip.detail}</TipNote>}
          </>
        ))}
      </div>
    </div>
  )
}
