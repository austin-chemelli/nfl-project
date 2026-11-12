/**
 * Who's stronger where (Matchups redesign, 2026-11-12): one row per stat, the offense's league rank on the
 * left and the defense's on the right, each as a bar that grows toward the middle with rank (1st = full).
 * A row where one side ranks at least eight places better carries a pill in that team's colour. Every rank
 * comes from the JSON (`face_off`, season to date before the game's week); this file only places marks.
 */
import type { FaceOffRow } from '../data/contract'
import { ordinal } from '../lib/rank'

/** Bar length from a rank: 1st of 32 is full, 32nd is a sliver. */
const share = (rank: number, n: number) => Math.max(0.06, (n + 1 - rank) / n)

export function FaceOff({
  rows,
  offense,
  defense,
  colorOf,
}: {
  rows: FaceOffRow[]
  offense: string
  defense: string
  colorOf: (team: string) => string
}) {
  if (rows.length === 0) return null
  const n = rows[0].n_teams
  return (
    <div data-testid="face-off" className="w-full">
      <div className="grid grid-cols-[3rem_minmax(0,1fr)_6.5rem_minmax(0,1fr)_3rem] items-center gap-x-2 pb-1 text-[11px] text-ink-3" aria-hidden>
        <span className="text-right">{offense} O</span>
        <span />
        <span className="text-center">rank of {n}</span>
        <span />
        <span>{defense} D</span>
      </div>
      {rows.map((r) => {
        const win = r.edge === 'offense' ? offense : r.edge === 'defense' ? defense : null
        return (
          <div
            key={r.id}
            data-testid={`face-${r.id}`}
            data-edge={r.edge}
            className="grid grid-cols-[3rem_minmax(0,1fr)_6.5rem_minmax(0,1fr)_3rem] items-center gap-x-2 border-b border-line py-1.5 text-[13px]"
            title={`${offense}'s ${r.off_noun}: ${ordinal(r.off_rank)} · ${defense}'s ${r.def_noun}: ${ordinal(r.def_rank)}`}
          >
            <span className={`tabular text-right ${r.edge === 'offense' ? 'font-semibold' : ''}`}>{ordinal(r.off_rank)}</span>
            <span className="relative h-2 rounded" style={{ background: 'var(--band)' }}>
              <span
                className="absolute right-0 top-0 h-2 rounded"
                style={{ width: `${100 * share(r.off_rank, n)}%`, background: colorOf(offense), opacity: r.edge === 'defense' ? 0.45 : 1 }}
              />
            </span>
            <span className="text-center text-[12px] leading-tight text-ink-2">
              {r.label}
              {win && (
                <span
                  data-testid="face-pill"
                  data-team={win}
                  className="ml-1 inline-block rounded-full border px-1.5 text-[10.5px] font-semibold"
                  style={{ borderColor: colorOf(win), color: 'var(--text-primary)' }}
                >
                  {win}
                </span>
              )}
            </span>
            <span className="relative h-2 rounded" style={{ background: 'var(--band)' }}>
              <span
                className="absolute left-0 top-0 h-2 rounded"
                style={{ width: `${100 * share(r.def_rank, n)}%`, background: colorOf(defense), opacity: r.edge === 'offense' ? 0.45 : 1 }}
              />
            </span>
            <span className={`tabular ${r.edge === 'defense' ? 'font-semibold' : ''}`}>{ordinal(r.def_rank)}</span>
          </div>
        )
      })}
    </div>
  )
}
