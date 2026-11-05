/** One line above the current slate: how last week went for the headline approach and the market. */
import { Link } from 'react-router'
import { useRecap, useSlate } from '../../data/api'
import type { Meta } from '../../data/contract'
import { HEADLINE } from '../../lib/models'
import { gameStatus, weekHref } from './helpers'

export function LastWeek({ meta, season, week }: { meta: Meta; season: number; week: number }) {
  const q = useRecap(season, week)
  const slate = useSlate(season, week)
  if (!q.data || !slate.data) return null
  const line = q.data.models.find((m) => m.model_id === HEADLINE)
  const mk = q.data.models.find((m) => m.model_id === 'market_baseline')
  if (!line || !mk) return null
  // a week scored after the fact isn't a live record, and the line mustn't read like one
  const replay = slate.data.games.some((g) => gameStatus(g).status !== 'locked')
  return (
    <p className="text-[14px] text-ink-2">
      <Link to={weekHref(meta, season, week)} className="text-accent hover:underline">
        Last week{replay ? ', scored after the fact' : ''}: the Student got {line.right} of {line.n} right, the market {mk.right} of {mk.n}.
      </Link>
    </p>
  )
}
