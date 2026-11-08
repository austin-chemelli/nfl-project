import { useParams } from 'react-router'
import { Loaded, Page } from '../components/ui'
import { useMeta } from '../data/api'
import { WeekView } from './slate/WeekView'

export default function SlatePage() {
  const params = useParams()
  const meta = useMeta()
  return (
    <Page
      title="Slate"
      docTitle={params.season && params.week ? `Week ${params.week}, ${params.season}` : 'This week'}
      lede="Four forecasting approaches predict every NFL game, lock in before kickoff, and get scored in public against the betting market. The Student, built from results instead of a persona, is the headline pick, chosen before the season; the tracker shows which approach leads so far."
    >
      <Loaded q={meta} what="slate" shape="slate">
        {(m) => {
          const season = params.season ? Number(params.season) : m.season
          const week = params.week ? Number(params.week) : m.current_week
          if (!Number.isInteger(season) || !Number.isInteger(week) || week < 1 || week > 22) return <p className="text-ink-2">That isn't a valid week.</p>
          return <WeekView meta={m} season={season} week={week} />
        }}
      </Loaded>
    </Page>
  )
}
