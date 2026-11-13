import type { ReactNode } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import { Navigate, useLocation, useParams } from 'react-router'
import { SummaryStrip, Tile } from '../components/SummaryStrip'
import { Tabs } from '../components/Tabs'
import { TeamAccent } from '../components/TeamAccent'
import { Card, Loaded, Page, PageSkeleton } from '../components/ui'
import { isNotFound, useLeague, useSimilar, useTeam, useTeams } from '../data/api'
import { TEAM_CODES, canonicalTeam, isTeam, teamInfo } from '../lib/teams'
import { recordText } from './league/helpers'
import { recordOf } from './league/playoffs'
import NotFoundPage from './NotFound'
import { Health } from './team/Health'
import { Games } from './team/Games'
import { Overview } from './team/Overview'
import { Staff } from './team/Staff'
import { callerTile, changeTile, healthTile, nextGameTile, playoffTile, type TileText } from './team/summary'
import { TeamPicker } from './team/TeamPicker'
import { callerChange } from './team/tendencies'
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
    callerTile(file.data?.units.off.caller, 'off', file.data && callerChange(file.data, 'off')?.start_week),
    callerTile(file.data?.units.def.caller, 'def', file.data && callerChange(file.data, 'def')?.start_week),
    changeTile(file.data),
    healthTile(file.data),
    nextGameTile(row),
  ].filter((t): t is TileText => t != null)

  const settled = !teams.isPending && !league.isPending && !file.isPending
  const noNumbers = <Card className="text-ink-2">Team numbers appear after the next data update.</Card>
  // The standings are rebuilt every site run; teams.json's records come from the last feature build and
  // can be a game behind, so the record shown everywhere on this page is the standings' when they load.
  const standing = league.data?.teams.find((t) => t.team === code)
  const line = standing
    ? [standing.div, recordOf(standing)].join(' · ')
    : row && [row.division, recordText(row), row.through_week != null ? `through Week ${row.through_week}` : null].filter(Boolean).join(' · ')

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
      <TeamPicker code={code} codes={TEAM_CODES} />
      {!settled ? (
        <PageSkeleton what={name} shape="tracker" title={false} />
      ) : (
        <>
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
              { id: 'overview', label: 'Overview', content: teams.data || league.data ? <Overview code={code} teams={teams.data} league={league.data} similar={similar.data} /> : noNumbers },
              { id: 'staff', label: 'Staff', content: <Part q={file} what="Staff details">{(f) => <Staff file={f} />}</Part> },
              ...(file.data?.health ? [{ id: 'health', label: 'Health', content: <Health file={file.data} /> }] : []),
              { id: 'tendencies', label: 'Tendencies', content: <Part q={file} what="Tendencies">{(f) => <Tendencies file={f} />}</Part> },
              { id: 'games', label: 'Games', content: <Games code={code} teams={teams.data} league={league.data} file={file.data} /> },
            ]}
          />
        </>
      )}
    </Page>
  )
}

/** One team (ADR 0022). Each file failing only removes what needs it. */
export default function TeamPage() {
  const { code = '' } = useParams()
  const { search } = useLocation()
  if (!isTeam(code)) return <NotFoundPage />
  const canon = canonicalTeam(code)
  if (canon !== code) return <Navigate to={`/team/${canon}${search}`} replace />
  // Availability merged into Health (M24.7): old links open Health
  if (new URLSearchParams(search).get('tab') === 'availability') return <Navigate to={`/team/${canon}?tab=health`} replace />
  return <Body key={canon} code={canon} />
}
