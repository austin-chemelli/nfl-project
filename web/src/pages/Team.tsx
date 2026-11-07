import type { ReactNode } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import { Navigate, useParams } from 'react-router'
import { SummaryStrip, Tile } from '../components/SummaryStrip'
import { Tabs } from '../components/Tabs'
import { TeamAccent } from '../components/TeamAccent'
import { Card, Loaded, Page } from '../components/ui'
import { isNotFound, useLeague, useSimilar, useTeam, useTeams } from '../data/api'
import { canonicalTeam, isTeam, teamInfo } from '../lib/teams'
import { recordText } from './league/helpers'
import NotFoundPage from './NotFound'
import { Games } from './team/Games'
import { Overview } from './team/Overview'
import { Staff } from './team/Staff'
import { callerTile, furthestTile, nextGameTile, playoffTile, type TileText } from './team/summary'
import { TeamPicker } from './team/TeamPicker'
import { Tendencies } from './team/Tendencies'

/** A tab that needs one file: not built yet reads as such, anything else is the usual error. */
function Part<T>({ q, what, children }: { q: UseQueryResult<T>; what: string; children: (d: T) => ReactNode }) {
  if (q.isError && isNotFound(q.error)) return <Card className="text-ink-2">{what} appear after the next data update.</Card>
  return (
    <Loaded q={q} what={what.toLowerCase()}>
      {children}
    </Loaded>
  )
}

function Body({ code }: { code: string }) {
  const teams = useTeams()
  const league = useLeague()
  const similar = useSimilar()
  const file = useTeam(code)
  const row = teams.data?.teams[code]
  const name = teamInfo(code).name

  const tiles = [
    playoffTile(league.data, code),
    callerTile(file.data?.units.off.caller, 'off'),
    callerTile(file.data?.units.def.caller, 'def'),
    furthestTile(file.data),
    nextGameTile(row),
  ].filter((t): t is TileText => t != null)

  const line = row && [row.division, recordText(row), row.through_week != null ? `through Week ${row.through_week}` : null].filter(Boolean).join(' · ')

  return (
    <Page
      docTitle={name}
      title={
        <span className="inline-flex flex-col gap-1">
          {name}
          <TeamAccent team={code} className="!w-14" />
        </span>
      }
      lede={line}
    >
      {teams.data && <TeamPicker code={code} codes={Object.keys(teams.data.teams)} />}
      {tiles.length > 0 && (
        <SummaryStrip label={`${name} summary`}>
          {tiles.map((t) => (
            <Tile key={t.label} label={t.label} value={t.value} sub={t.sub} tab={t.tab} />
          ))}
        </SummaryStrip>
      )}
      <Tabs
        label={`${name} views`}
        default="overview"
        tabs={[
          { id: 'overview', label: 'Overview', content: <Part q={teams} what="Team numbers">{(t) => <Overview code={code} teams={t} league={league.data} similar={similar.data} />}</Part> },
          { id: 'staff', label: 'Staff', content: <Part q={file} what="Staff details">{(f) => <Staff file={f} />}</Part> },
          { id: 'tendencies', label: 'Tendencies', content: <Part q={file} what="Tendencies">{(f) => <Tendencies file={f} />}</Part> },
          { id: 'games', label: 'Games', content: <Part q={teams} what="Games">{(t) => <Games code={code} teams={t} league={league.data} file={file.data} />}</Part> },
        ]}
      />
    </Page>
  )
}

/** One team (ADR 0022). Each file failing only removes what needs it. */
export default function TeamPage() {
  const { code = '' } = useParams()
  if (!isTeam(code)) return <NotFoundPage />
  const canon = canonicalTeam(code)
  if (canon !== code) return <Navigate to={`/team/${canon}`} replace />
  return <Body key={canon} code={canon} />
}
