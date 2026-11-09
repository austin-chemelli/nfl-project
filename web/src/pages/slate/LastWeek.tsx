/** One line above the current slate: how last week went for the headline approach and the market. */
import { Link } from 'react-router'
import { useRecap, useSlate } from '../../data/api'
import type { Meta } from '../../data/contract'
import { Help } from '../../components/Help'
import { HEADLINE, SHORT } from '../../lib/models'
import { gameStatus, weekHref } from './helpers'

export function LastWeek({ meta, season, week }: { meta: Meta; season: number; week: number }) {
  const q = useRecap(season, week)
  const slate = useSlate(season, week)
  if (!q.data || !slate.data) return null
  const line = q.data.models.find((m) => m.model_id === HEADLINE)
  const mk = q.data.models.find((m) => m.model_id === 'market_baseline')
  if (!line || !mk) return null
  // a week scored after the fact isn't a live record, and the help must say so
  const replay = slate.data.games.some((g) => gameStatus(g).status !== 'locked')
  return (
    <p className="text-[14px] text-ink-2">
      <Link to={weekHref(meta, season, week)} className="text-accent hover:underline">
        Last week{replay ? ' (backfill)' : ''}: {SHORT[HEADLINE]} {line.right} of {line.n} right, market {mk.right} of {mk.n}.
      </Link>
      <Help text={replay ? "Not a live record: these games had no lock, so the picks were scored after the fact." : 'Picks come from the locks; results are scored after the games.'} />
    </p>
  )
}
