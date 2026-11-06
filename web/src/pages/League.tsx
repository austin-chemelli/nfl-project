import { Tabs } from '../components/Tabs'
import { Card, Loaded, Page } from '../components/ui'
import { isNotFound, useTeams } from '../data/api'
import { Teams } from './league/Teams'

/** Where the league stands (ADR 0019). Each tab arrives with its data; none renders before that. */
export default function LeaguePage() {
  const q = useTeams()
  return (
    <Page title="League" lede="Where all 32 teams stand.">
      {q.isError && isNotFound(q.error) ? (
        <Card className="text-ink-2">Team charts appear after the next data update.</Card>
      ) : (
        <Loaded q={q} what="teams">
          {(t) => <Tabs label="League views" default="teams" tabs={[{ id: 'teams', label: 'Teams', content: <Teams file={t} /> }]} />}
        </Loaded>
      )}
    </Page>
  )
}
