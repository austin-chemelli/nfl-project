import { Link } from 'react-router'
import { Section, TableScroll, td, th } from '../../components/ui'
import type { Tracker } from '../../data/contract'

const pts = (v: number | null) => (v == null ? '–' : v.toFixed(1))
const signed = (v: number | null) => (v == null ? '–' : `${v > 0 ? '+' : ''}${v.toFixed(1)}`)

/** Claims about a listed starter being ruled out, graded by how far the line then moved (ADR 0027). */
export function PlayerClaims({ t }: { t: Tracker }) {
  const pc = t.player_claims
  if (!pc) return null
  return (
    <Section title="Player claims" help="When a listed starter is ruled out we say how many points the line should move toward the opponent. Graded once the consensus line has reacted.">
      <p className="m-0 mb-3 text-ink-2">When a listed starter is ruled out, we said how far the line should move; here is how far it did.</p>
      <p className="m-0 mb-3 text-ink">
        <span className="tabular">{pc.claims}</span> claims made, <span className="tabular">{pc.graded}</span> graded
        {pc.graded > 0 && pc.mean_expected != null && pc.mean_moved != null && (
          <>. On average we said <span className="tabular">{pts(pc.mean_expected)}</span> points; the line moved <span className="tabular">{pts(pc.mean_moved)}</span>.</>
        )}
      </p>
      {pc.graded === 0 ? (
        <p className="text-ink-2">No claim has been graded yet. Claims are counted from {pc.first_pass.slice(0, 10)}.</p>
      ) : (
        <TableScroll>
          <table className="w-full border-collapse text-[14px]">
            <thead>
              <tr>
                <th className={th}>Week</th>
                <th className={th}>Player</th>
                <th className={`${th} hidden sm:table-cell`}>Status before</th>
                <th className={th}>Said</th>
                <th className={th}>Moved</th>
                <th className={`${th} hidden sm:table-cell`}>Margin vs line</th>
              </tr>
            </thead>
            <tbody>
              {pc.rows.map((r) => (
                <tr key={`${r.game_id}-${r.team}-${r.player}`}>
                  <td className={`${td} tabular`}>{r.week}</td>
                  <td className={`${td} break-words`}>
                    <Link to={`/game/${r.game_id}`}>{r.player}</Link> <span className="text-[13px] text-ink-3">{r.team}</span>
                  </td>
                  <td className={`${td} hidden sm:table-cell`}>{r.status_before}</td>
                  <td className={`${td} tabular`}>{pts(r.expected)}</td>
                  <td className={`${td} tabular`}>{pts(r.moved)}</td>
                  <td className={`${td} tabular hidden sm:table-cell`}>{signed(r.margin_vs_line)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableScroll>
      )}
    </Section>
  )
}
