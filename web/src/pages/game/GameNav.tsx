/** Previous / next game of the same week, above the matchup banner; keeps the open tab. Neutral colors: on a game, color means the team. */
import { useEffect } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { useMeta, useSlate } from '../../data/api'
import { weekHref } from '../slate/helpers'
import { arrowStepsGames, gameHref, slateNeighbours, weekOf, type NavGame } from './gameNav'

export function GameNav({ id }: { id: string | undefined }) {
  const wk = weekOf(id)
  const slate = useSlate(wk?.season, wk?.week)
  const meta = useMeta()
  const [params] = useSearchParams()
  const nav = useNavigate()
  const tab = params.get('tab')
  const n = id && slate.data ? slateNeighbours(slate.data.games, id) : null
  const prev = n?.prev ? gameHref(n.prev.game_id, tab) : null
  const next = n?.next ? gameHref(n.next.game_id, tab) : null

  useEffect(() => {
    if (!prev && !next) return
    const onKey = (e: KeyboardEvent) => {
      if (!arrowStepsGames(e)) return
      const to = e.key === 'ArrowLeft' ? prev : next
      if (!to) return
      e.preventDefault()
      nav(to)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [prev, next, nav])

  if (!wk) return null
  const slateHref = meta.data ? weekHref(meta.data, wk.season, wk.week) : `/week/${wk.season}/${wk.week}`
  // one fixed-height row from the first paint, so the banner below never moves when the slate arrives
  return (
    <nav aria-label="Games this week" className="mb-2 grid h-8 grid-cols-[1fr_auto_1fr] items-center gap-2 text-[13px]">
      <div className="min-w-0">{n?.prev && prev && <Step to={prev} g={n.prev} dir="prev" />}</div>
      <Link to={slateHref} className="whitespace-nowrap text-ink-3 hover:text-ink hover:underline" title="Back to the week's slate">
        <span className="tabular">{n && n.index >= 0 ? `Week ${wk.week} · ${n.index + 1} of ${n.total}` : `Week ${wk.week}`}</span>
      </Link>
      <div className="flex min-w-0 justify-end">{n?.next && next && <Step to={next} g={n.next} dir="next" />}</div>
    </nav>
  )
}

function Step({ to, g, dir }: { to: string; g: NavGame; dir: 'prev' | 'next' }) {
  const label = `${g.away} @ ${g.home}`
  return (
    <Link
      to={to}
      rel={dir}
      aria-label={`${dir === 'prev' ? 'Previous' : 'Next'} game: ${label}`}
      title={`${dir === 'prev' ? 'Previous' : 'Next'} game (${dir === 'prev' ? '←' : '→'} key)`}
      className="inline-flex max-w-full items-center gap-1 truncate whitespace-nowrap rounded-md border border-line bg-surface-1 px-2.5 py-1 font-medium text-ink-2 hover:bg-surface-2 hover:text-ink hover:no-underline"
    >
      {dir === 'prev' && <span aria-hidden>←</span>}
      <span className="truncate">{label}</span>
      {dir === 'next' && <span aria-hidden>→</span>}
    </Link>
  )
}
