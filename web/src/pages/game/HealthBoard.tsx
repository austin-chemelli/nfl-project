/**
 * The Health tab's matchup board (Austin 2026-11-15, Option A of the mock): per side of the ball, each
 * offensive room against the defensive room that faces it (receivers and corners, tight ends and backs
 * against linebackers, the line against the edge and the interior). Each room is a bar of its league rank
 * (longer is better): faint at full strength, solid now with the listed absences, so "usually good, weak
 * now" shows as a long faint bar over a short solid one. The pill says which room ranks better now; a
 * flagged pair is shaded and carries its template sentence. Every number and sentence comes from
 * `health.board` (nfl/players/mismatch.py); team color through `[data-matchup]`.
 */
import type { BoardRow, HealthBoard } from '../../data/contract'

const w = (rank: number) => `${((33 - rank) / 32) * 100}%`
// short names for the bars (the side's heading already names each team); the sentences keep the long ones
const SHORT: Record<string, string> = { OL: 'line', EDGE: 'edge', DL: 'interior', TE: 'tight ends', WR: 'receivers', RB: 'backs', LB: 'linebackers', CB: 'corners', S: 'safeties' }

function Bar({ room, color, side }: { room: BoardRow['offense']; color: string; side: 'left' | 'right' }) {
  const anchor = side === 'left' ? { right: 0 } : { left: 0 }
  const moved = room.now_rank !== room.rank
  const out = room.missing.filter((m) => m.out).map((m) => m.player)
  const align = side === 'left' ? 'text-right' : ''
  return (
    <div className="min-w-0" data-room={`${room.team}-${room.grp}`}>
      <div className={`mb-0.5 truncate text-[12px] text-ink-2 ${align}`} title={`${room.team} ${room.name}`}>{SHORT[room.grp] ?? room.name}</div>
      <div className="relative h-2.5 rounded-sm" style={{ background: 'var(--band)' }} aria-hidden>
        <i className="absolute top-0 h-2.5 rounded-sm opacity-30" style={{ ...anchor, width: w(room.rank), background: color }} />
        <i className="absolute top-0 h-2.5 rounded-sm" style={{ ...anchor, width: w(room.now_rank), background: color }} />
      </div>
      <div className={`mt-0.5 truncate text-[11px] text-ink-3 ${align}`}>
        <span className="tabular font-medium text-ink" title={`#${room.rank} (${room.label}) at full strength${moved ? `; about #${room.now_rank} (${room.now_label}) now` : ''}`}>
          {moved ? <>#{room.rank} → ~#{room.now_rank}</> : <>#{room.rank}</>}
        </span>
        {out.length > 0 && <> · out: {out.join(', ')}</>}
      </div>
    </div>
  )
}

function Verdict({ r, colorOf }: { r: BoardRow; colorOf: (team: string) => string }) {
  return (
    <div className="text-center text-[11px] leading-tight text-ink-3">
      {r.favours ? (
        <span data-testid="board-verdict" data-team={r.favours} className="inline-block rounded-full border px-1.5 font-medium text-ink" style={{ borderColor: colorOf(r.favours) }}>
          {r.favours} edge
        </span>
      ) : (
        <span data-testid="board-verdict" className="inline-block rounded-full border border-line px-1.5">even</span>
      )}
      {r.moved && <div className="mt-0.5">injuries moved it</div>}
    </div>
  )
}

export function HealthBoardView({ board, colorOf }: { board: HealthBoard; colorOf: (team: string) => string }) {
  return (
    <div data-testid="health-board" className="flex max-w-4xl flex-col gap-5">
      {board.lede && (
        <p className="m-0 max-w-3xl text-[14px] text-ink">
          <span className="font-semibold">{board.lede_kind === 'gap' ? 'The widest gap: ' : 'The biggest change: '}</span>
          {board.lede}
        </p>
      )}
      {board.sides.map((s) => (
        <div key={s.offense} data-testid={`board-${s.offense}`}>
          <h3 className="m-0 mb-1 flex items-center gap-2 text-[14px] font-semibold">
            <span className="inline-block h-3 w-3 rounded-sm" style={{ background: colorOf(s.offense) }} />
            {s.offense} offense <span className="font-normal text-ink-3">vs</span>
            <span className="inline-block h-3 w-3 rounded-sm" style={{ background: colorOf(s.defense) }} />
            {s.defense} defense
          </h3>
          <ul className="m-0 list-none p-0">
            {s.rows.map((r) => (
              <li
                key={`${r.offense.grp}-${r.defense.grp}`}
                data-testid={`board-row-${s.offense}-${r.offense.grp}-${r.defense.grp}`}
                data-flag={r.flag || undefined}
                className={`border-b border-line px-1 py-2 ${r.flag ? 'rounded bg-[color-mix(in_srgb,var(--warning)_9%,transparent)]' : ''}`}
              >
                <div className="grid grid-cols-[minmax(0,1fr)_5.5rem_minmax(0,1fr)] items-center gap-2">
                  <Bar room={r.offense} color={colorOf(r.offense.team)} side="left" />
                  <Verdict r={r} colorOf={colorOf} />
                  <Bar room={r.defense} color={colorOf(r.defense.team)} side="right" />
                </div>
                {r.sentence && r.sentence !== board.lede && <p className="m-0 mt-1 text-[12px] text-ink-2">{r.sentence}</p>}
              </li>
            ))}
          </ul>
        </div>
      ))}
      {board.notes.map((n) => <p key={n} className="m-0 text-[13px] text-ink-2">{n}</p>)}
      <p className="m-0 text-[12px] text-ink-3">
        Each bar is a room&apos;s league rank, longer is better: faint at full strength, solid now with this week&apos;s absences.
        {' '}A pill names the room ranked 6+ places better now; a shaded row is 12+ places apart or moved 8+ by injuries.
      </p>
    </div>
  )
}
