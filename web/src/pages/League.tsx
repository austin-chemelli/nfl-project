import type { ReactNode } from 'react'
import { SummaryStrip, Tile } from '../components/SummaryStrip'
import { Tabs } from '../components/Tabs'
import { Card, Loaded, Page } from '../components/ui'
import { isNotFound, useLeague, useTeams } from '../data/api'
import type { LeagueFile } from '../data/contract'
import { fmtProb } from './league/playoffs'
import { Games } from './league/Games'
import { Odds } from './league/Odds'
import { Similar } from './league/Similar'
import { Standings } from './league/Standings'
import { closestRace, gameOfWeek, topSeed } from './league/summary'
import { Teams } from './league/Teams'

/** The tiles that the file can answer; each opens the tab that explains it. */
function Strip({ file }: { file: LeagueFile }) {
  const afc = topSeed(file, 'AFC')
  const nfc = topSeed(file, 'NFC')
  const race = closestRace(file)
  const game = gameOfWeek(file)
  const tiles: ReactNode[] = []
  if (afc) tiles.push(<Tile key="afc" label="AFC favorite for the 1 seed" value={afc.team} sub={`${fmtProb(afc.p)} to get it`} tab="odds" />)
  if (nfc) tiles.push(<Tile key="nfc" label="NFC favorite for the 1 seed" value={nfc.team} sub={`${fmtProb(nfc.p)} to get it`} tab="odds" />)
  if (race) tiles.push(<Tile key="race" label="Closest division race" value={race.division} sub={`${race.leader.team} ${fmtProb(race.leader.p)}, ${race.runnerUp.team} ${fmtProb(race.runnerUp.p)}`} tab="standings" />)
  if (game) tiles.push(<Tile key="game" label="Biggest game this week" value={`${game.away} @ ${game.home}`} sub={`Week ${game.week}, by how far it moves playoff odds`} tab="games" />)
  return tiles.length ? <SummaryStrip label="League summary">{tiles}</SummaryStrip> : null
}

/** Where the league stands (ADR 0019). Teams comes from teams.json; the playoff tabs need league.json and say so when it's missing. */
export default function LeaguePage() {
  const teams = useTeams()
  const league = useLeague()

  const playoffTab = (what: string, render: (f: LeagueFile) => ReactNode) =>
    league.isError && isNotFound(league.error) ? (
      <Card className="text-ink-2">{what === 'standings' ? 'Standings appear' : what === 'games' ? 'Games that matter appear' : what === 'similar' ? 'Similar seasons appear' : 'Playoff odds appear'} after the next data update.</Card>
    ) : (
      <Loaded q={league} what={what}>
        {render}
      </Loaded>
    )

  const teamsTab =
    teams.isError && isNotFound(teams.error) ? (
      <Card className="text-ink-2">Team charts appear after the next data update.</Card>
    ) : (
      <Loaded q={teams} what="teams">
        {(t) => <Teams file={t} />}
      </Loaded>
    )

  return (
    <Page title="League" lede="Where all 32 teams stand.">
      {league.data && <Strip file={league.data} />}
      <Tabs
        label="League views"
        default="odds"
        tabs={[
          { id: 'odds', label: 'Playoff odds', content: playoffTab('odds', (f) => <Odds file={f} />) },
          { id: 'teams', label: 'Team charts', content: teamsTab },
          { id: 'standings', label: 'Standings', content: playoffTab('standings', (f) => <Standings file={f} />) },
          { id: 'games', label: 'Games that matter', content: playoffTab('games', (f) => <Games file={f} />) },
          { id: 'similar', label: 'Similar seasons', content: playoffTab('similar', (f) => <Similar file={f} />) },
        ]}
      />
    </Page>
  )
}
