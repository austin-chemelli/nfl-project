/**
 * How strong each position room is (M24.7 round 3, PR B): a league rank at full strength and the
 * estimate now with the room's injuries, on a 32-to-1 track (better to the right). A filled dot is
 * the full-strength rank; a hollow one, joined by a line, the estimate now. Hover a room for the
 * stats behind its grade. Context only (ADR 0027).
 */
import { TipRow, TipTitle, useChartTip } from '../../charts/ChartTip'
import type { RoomGrade } from '../../data/contract'
import { GROUP, GROUP_ORDER } from '../../lib/health'

const at = (rank: number) => `${((32 - rank) / 31) * 100}%`

function fmt(key: string, v: number): string {
  if (key.endsWith('_epa')) return `${v >= 0 ? '+' : ''}${v.toFixed(2)}`
  if (key.endsWith('_ybc') || key.endsWith('_ypt')) return `${v.toFixed(1)} yds`
  return `${(100 * v).toFixed(1)}%`
}

function Tip({ r }: { r: RoomGrade }) {
  const basis = r.basis === 'players' ? `its full-strength starters' plays, this season and last (${r.plays ?? 0})` : `this season's team stats, ${r.games ?? 0} games near full strength`
  return (
    <>
      <TipTitle note={`#${r.rank} ${r.label} at full strength`}>{GROUP[r.grp] ?? r.grp}</TipTitle>
      {r.stats.map((s) => <TipRow key={s.key} value={fmt(s.key, s.value)} label={`${s.label} · #${s.rank}`} />)}
      {r.now_rank !== r.rank && <TipRow value={`~#${r.now_rank}`} label={`now, with ${Math.round(100 * (r.health ?? 1))}% of the room available`} />}
      <div className="mt-1 text-[12px] text-ink-3">From {basis}.</div>
    </>
  )
}

export function Rooms({ rooms }: { rooms: RoomGrade[] }) {
  const { box, at: hov, bind, card } = useChartTip()
  const order = new Map(GROUP_ORDER.map((g, i) => [g, i]))
  const rows = [...rooms].sort((a, b) => (order.get(a.grp) ?? 99) - (order.get(b.grp) ?? 99))
  const hovered = rows.find((r) => r.grp === hov?.key)
  return (
    <div ref={box} className="relative">
      <div className="mb-1 grid grid-cols-[minmax(0,7.5rem)_minmax(0,1fr)_6.5rem] gap-x-3 text-[11px] uppercase tracking-wide text-ink-3">
        <span />
        <span className="flex justify-between"><span>#32</span><span>#1</span></span>
        <span className="text-right">full → now</span>
      </div>
      <ul className="m-0 flex list-none flex-col gap-1.5 p-0" data-testid="health-rooms">
        {rows.map((r) => {
          const drop = r.now_rank - r.rank
          const lo = Math.min(r.rank, r.now_rank)
          const hi = Math.max(r.rank, r.now_rank)
          return (
            <li key={r.grp} {...bind(r.grp)} data-room={r.grp} className="grid grid-cols-[minmax(0,7.5rem)_minmax(0,1fr)_6.5rem] items-center gap-x-3 rounded py-0.5 text-[14px] hover:bg-[var(--surface-2)]">
              <span className="truncate text-ink-2">{GROUP[r.grp] ?? r.grp}</span>
              <span className="relative h-4" role="img" aria-label={`${GROUP[r.grp] ?? r.grp}: number ${r.rank} at full strength${drop ? `, about ${r.now_rank} now` : ''}`}>
                <span className="absolute inset-x-0 top-1/2 h-px bg-[var(--border)]" />
                {[8.5, 16.5, 24.5].map((q) => <span key={q} className="absolute top-1 h-2 w-px bg-[var(--border)]" style={{ left: at(q) }} />)}
                {drop !== 0 && <span className="absolute top-1/2 h-0.5 -translate-y-1/2 bg-[var(--warning)]" style={{ left: at(hi), right: `calc(100% - ${at(lo)})` }} />}
                {drop !== 0 && <span data-now className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[var(--warning)] bg-[var(--surface-1)]" style={{ left: at(r.now_rank) }} />}
                <span className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--accent)]" style={{ left: at(r.rank) }} />
              </span>
              <span className="tabular text-right text-[13px]">
                <span className="text-ink">#{r.rank}</span>
                {drop !== 0 ? <span className="font-medium text-ink"> → ~#{r.now_rank}</span> : <span className="text-ink-3"> {r.label}</span>}
              </span>
            </li>
          )
        })}
      </ul>
      {hovered && card(<Tip r={hovered} />)}
    </div>
  )
}
