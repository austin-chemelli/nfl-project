import { Link } from 'react-router'
import { TableScroll, td, th } from '../../components/ui'
import type { LeagueFile } from '../../data/contract'
import { teamInfo } from '../../lib/teams'
import { divisionTables, recordOf, type Conf } from './playoffs'

/** The Standings tab: eight division tables as they stand today (ADR 0019). */
export function Standings({ file }: { file: LeagueFile }) {
  return (
    <div className="flex min-w-0 flex-col gap-6">
      <p className="text-ink-2">Records by division, leader first{file.through_week != null ? `, through Week ${file.through_week}` : ''}.</p>
      {(['AFC', 'NFC'] as Conf[]).map((conf) => (
        <section key={conf} aria-label={`${conf} standings`} className="grid min-w-0 gap-4 md:grid-cols-2">
          {divisionTables(file.teams, conf).map(({ division, teams }) => (
            <div key={division} className="min-w-0">
              <h3 className="mb-1 text-[15px] font-medium text-ink">{division}</h3>
              <TableScroll>
                <table className="w-full border-collapse text-[13px]">
                  <thead>
                    <tr>
                      <th className={th}>Team</th>
                      <th className={`${th} text-right`}>W-L-T</th>
                      <th className={`${th} text-right`}>Div</th>
                      <th className={`${th} text-right`}>Conf</th>
                      <th className={`${th} text-right`}>PF</th>
                      <th className={`${th} text-right`}>PA</th>
                      <th className={`${th} text-right`}>Left</th>
                    </tr>
                  </thead>
                  <tbody>
                    {teams.map((t) => (
                      <tr key={t.team}>
                        <td className={td} title={teamInfo(t.team).name}>
                          <Link to={`/league?tab=teams&team=${t.team}`}>{t.team}</Link>
                        </td>
                        <td className={`${td} tabular text-right`}>{recordOf(t).replaceAll('–', '-')}</td>
                        <td className={`${td} tabular text-right`}>{t.div_rec}</td>
                        <td className={`${td} tabular text-right`}>{t.conf_rec}</td>
                        <td className={`${td} tabular text-right`}>{t.pf}</td>
                        <td className={`${td} tabular text-right`}>{t.pa}</td>
                        <td className={`${td} tabular text-right`}>{t.left}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableScroll>
            </div>
          ))}
        </section>
      ))}
    </div>
  )
}
