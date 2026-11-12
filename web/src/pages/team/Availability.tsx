import { FinePrint } from '../../components/FinePrint'
import { TableScroll, td, th } from '../../components/ui'
import type { TeamFile } from '../../data/contract'
import { Block } from './Block'

type Availability = NonNullable<TeamFile['availability']>

const pts = (v: number) => v.toFixed(1)
const pct = (v: number | null) => (v == null ? '–' : `${Math.round(100 * v)}%`)

/** The team's most valuable starters, what each is worth in points of spread, and who is on the injury report (ADR 0027). */
export function Availability({ file }: { file: TeamFile }) {
  const a: Availability | null = file.availability
  if (!a) return null
  const lede = !a.reported || a.value_at_risk == null
    ? 'No injury report yet this week.'
    : a.value_at_risk > 0
      ? `${pts(a.value_at_risk)} points of value at risk this week, from the most valuable starters on the injury report.`
      : 'None of the starters we score is on this week\'s injury report.'
  return (
    <div className="flex flex-col gap-8">
      <Block title={`Availability, Week ${a.week}`} line={lede}>
        {a.players.length > 0 && (
          <TableScroll>
            <table className="w-full border-collapse text-[14px]">
              <thead>
                <tr>
                  <th className={th}>Player</th>
                  <th className={th}>Group</th>
                  <th className={th}>Value, pts</th>
                  <th className={th}>Status</th>
                  <th className={`${th} hidden sm:table-cell`}>Plays when listed so</th>
                  <th className={`${th} hidden sm:table-cell`}>At risk, pts</th>
                </tr>
              </thead>
              <tbody>
                {a.players.map((p) => (
                  <tr key={`${p.player}-${p.grp}`}>
                    <td className={`${td} break-words font-medium`}>{p.player}</td>
                    <td className={td}>{p.grp}</td>
                    <td className={`${td} tabular`}>{pts(p.value_pts)}</td>
                    <td className={td}>{a.reported && p.status ? p.status : '–'}</td>
                    <td className={`${td} tabular hidden sm:table-cell`}>{a.reported && p.status ? pct(p.p_play) : '–'}</td>
                    <td className={`${td} tabular hidden sm:table-cell`}>{a.reported && p.status && p.at_risk != null ? pts(p.at_risk) : '–'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableScroll>
        )}
      </Block>
      {a.reported && a.listed.length > 0 && (
        <Block title="Listed starters">
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {a.listed.map((k) => (
              <li key={`${k.player}-${k.grp}`} className="border-b border-line pb-2 text-ink">{k.sentence}</li>
            ))}
          </ul>
        </Block>
      )}
      <FinePrint>
        <p>Value is what the player is worth to the team in points of spread over a typical replacement, from his production, contract and share of snaps in games before this week. Plays when listed so is how often players with that status have played since 2016. A player not on the injury report shows no status.</p>
      </FinePrint>
    </div>
  )
}
