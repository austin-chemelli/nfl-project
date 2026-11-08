import { useParams } from 'react-router'
import { Help } from '../components/Help'
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
      lede={
        <>
          Four forecasting approaches pick every NFL game before kickoff and are scored in public against the betting market.{' '}
          <Help text="The Student learns from results instead of a persona. It was chosen as the headline pick before the season; the Tracker shows which approach leads now." />
        </>
      }
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
