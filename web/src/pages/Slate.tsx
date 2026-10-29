import { useParams } from 'react-router'
import { Loaded, Page } from '../components/ui'
import { useMeta } from '../data/api'
import { WeekView } from './slate/WeekView'

export default function SlatePage() {
  const params = useParams()
  const meta = useMeta()
  return (
    <Page title="Slate" lede="Every game of the week: what each approach picks, how far it sits from the betting market, and who is right once the game is final.">
      <Loaded q={meta} what="site info">
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
