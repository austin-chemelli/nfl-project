/**
 * How strong each position room is (M24.7 round 3, PR B): a league rank at full strength and the
 * estimate now with the room's injuries, as a bullet bar (longer is better): the solid bar is the
 * rank now, the faint bar behind it the full-strength rank, so the gap is what the injuries cost; both
 * ranks are printed beside it, and under it how much of the room is available this week and who is
 * missing or in doubt (this replaced the separate health bars). Hover a room for the
 * stats behind its grade. Context only (ADR 0027).
 */
import { TipRow, TipTitle, useChartTip } from '../../charts/ChartTip'
import type { RoomGrade, TeamHealth } from '../../data/contract'
import { GROUP, GROUP_ORDER, tone } from '../../lib/health'

function fmt(key: string, v: number): string {
  if (key.endsWith('_epa')) return `${v >= 0 ? '+' : ''}${v.toFixed(2)}`
  if (key.endsWith('_ybc') || key.endsWith('_ypt')) return `${v.toFixed(1)} yds`
  return `${(100 * v).toFixed(1)}%`
}

function Tip({ r }: { r: RoomGrade }) {
  const unit = ['EDGE', 'DL', 'LB', 'CB', 'S'].includes(r.grp) ? 'snaps' : 'plays'
  const basis = r.basis === 'players'
    ? `its full-strength starters' own ${unit}, this season and last (${(r.plays ?? 0).toLocaleString('en-US')}), wherever they played`
    : `this season's team stats, ${r.games ?? 0} games near full strength`
  return (
    <>
      <TipTitle note={`#${r.rank} ${r.label} at full strength`}>{GROUP[r.grp] ?? r.grp}</TipTitle>
      {r.stats.map((s) => <TipRow key={s.key} value={fmt(s.key, s.value)} label={`${s.label} · #${s.rank}`} />)}
      {r.now_rank !== r.rank && <TipRow value={`~#${r.now_rank}`} label={`now, with ${Math.round(100 * (r.health ?? 1))}% of the room available`} />}
      <div className="mt-1 text-[12px] text-ink-3">From {basis}.</div>
    </>
  )
}

// longer is better: #1 fills the track, #32 barely starts it
const w = (rank: number) => `${((33 - rank) / 32) * 100}%`
const COLS = 'grid grid-cols-[minmax(0,6.5rem)_minmax(0,1fr)_3.25rem_3.25rem] items-center gap-x-3'
// the label bands' edges (elite to #6, good to #14, average to #24)
const BANDS = [
  { label: 'weak', from: 32, to: 25 }, { label: 'average', from: 24, to: 15 },
  { label: 'good', from: 14, to: 7 }, { label: 'elite', from: 6, to: 1 },
]

const pct = (v: number) => `${Math.round(100 * v)}%`
const star = (s: { player: string; key: boolean }) => (s.key ? `${s.player} ★` : s.player)

/** Under a room's bar: how much of it is available and who is missing or in doubt. */
function Missing({ h, grp }: { h: TeamHealth['now']; grp: string }) {
  const g = h.groups.find((x) => x.grp === grp)
  const rows = h.starters.filter((s) => s.grp === grp)
  const out = rows.filter((s) => tone(s) === 'out' || tone(s) === 'iffy').map(star)
  const doubt = rows.filter((s) => s.doubt).map(star)
  if (out.length === 0 && doubt.length === 0) return null
  return (
    <span className="col-start-2 col-end-5 -mt-0.5 text-[12px] text-ink-3">
      {out.length > 0 && <><span className="font-medium text-ink-2">{pct(g?.health ?? 1)} available</span>: missing {out.join(', ')} ({out.length} of {g?.starters || rows.length})</>}
      {out.length > 0 && doubt.length > 0 && '; '}
      {doubt.length > 0 && (
        <span data-doubt className="inline-flex items-center gap-1">
          <span aria-hidden className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--warning)]" />in doubt (practice) {doubt.join(', ')}
        </span>
      )}
    </span>
  )
}

export function Rooms({ rooms, h }: { rooms: RoomGrade[]; h: TeamHealth['now'] }) {
  const { box, at: hov, bind, card } = useChartTip()
  const order = new Map(GROUP_ORDER.map((g, i) => [g, i]))
  const rows = [...rooms].sort((a, b) => (order.get(a.grp) ?? 99) - (order.get(b.grp) ?? 99))
  const ungraded = h.groups.filter((g) => !rooms.some((r) => r.grp === g.grp))
  const hovered = rows.find((r) => r.grp === hov?.key)
  const ghost = 'color-mix(in srgb, var(--accent) 22%, transparent)'
  return (
    <div ref={box} className="relative">
      {rows.length > 0 && <div className={`${COLS} mb-1 text-[11px] uppercase tracking-wide text-ink-3`}>
        <span />
        <span className="relative flex h-4 max-sm:invisible">
          {BANDS.map((b) => (
            <span key={b.label} className="truncate border-l border-[var(--border)] pl-1 first:border-l-0 first:pl-0" style={{ width: `calc(${w(b.to)} - ${w(b.from + 1)})` }}>{b.label}</span>
          ))}
        </span>
        <span className="text-right text-ink-2">Now</span>
        <span className="text-right">Full</span>
      </div>}
      <ul className="m-0 flex list-none flex-col gap-1 p-0" data-testid="health-rooms">
        {rows.map((r) => {
          const drop = r.now_rank - r.rank
          return (
            <li key={r.grp} {...bind(r.grp)} data-room={r.grp} className={`${COLS} gap-y-1 rounded py-1 text-[14px] hover:bg-[var(--surface-2)]`}>
              <span className="truncate text-ink-2">{GROUP[r.grp] ?? r.grp}</span>
              <span className="relative h-3.5 rounded-sm bg-[var(--surface-2)]" role="img" aria-label={`${GROUP[r.grp] ?? r.grp}: about number ${r.now_rank} now, number ${r.rank} at full strength`}>
                {BANDS.slice(1).map((b) => <span key={b.label} className="absolute inset-y-0 w-px bg-[var(--border)]" style={{ left: w(b.from + 1) }} />)}
                {drop > 0 && <span data-full className="absolute inset-y-0 left-0 rounded-sm" style={{ width: w(r.rank), background: ghost, boxShadow: 'inset -2px 0 0 var(--accent)' }} />}
                <span data-now className="absolute inset-y-0 left-0 rounded-sm bg-[var(--accent)]" style={{ width: w(r.now_rank) }} />
              </span>
              <span className="tabular text-right">
                <span className="font-semibold text-ink">{drop > 0 ? '~' : ''}#{r.now_rank}</span>
              </span>
              <span className={`tabular text-right text-[13px] ${drop > 0 ? 'text-ink-2' : 'text-ink-3'}`}>#{r.rank}</span>
              <Missing h={h} grp={r.grp} />
            </li>
          )
        })}
        {ungraded.map((g) => (
          <li key={g.grp} data-room={g.grp} className={`${COLS} py-1 text-[14px]`}>
            <span className="truncate text-ink-2">{GROUP[g.grp] ?? g.grp}</span>
            <span className="text-[12px] text-ink-3">not graded</span>
            <span /><span />
            <Missing h={h} grp={g.grp} />
          </li>
        ))}
      </ul>
      {rows.length > 0 && <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-ink-3">
        <span className="inline-flex items-center gap-1.5"><span aria-hidden className="inline-block h-2.5 w-5 rounded-sm bg-[var(--accent)]" />now, with this week&apos;s injuries (an estimate)</span>
        <span className="inline-flex items-center gap-1.5"><span aria-hidden className="inline-block h-2.5 w-5 rounded-sm" style={{ background: ghost, boxShadow: 'inset -2px 0 0 var(--accent)' }} />at full strength: what the injuries cost</span>
        <span>Longer is better; ranks are against the other 31 teams.</span>
      </div>}
      {hovered && card(<Tip r={hovered} />)}
    </div>
  )
}
