import type { Game } from '../../data/contract'
import { newsLine, NEWS_NAME } from './news'

/** One line under the Student's pick: the football-only spread and what the capped news adjustment moved it. */
export function NewsLine({ g }: { g: Game }) {
  const l = newsLine(g)
  if (!l) return null
  return (
    <p className="mb-3 max-w-3xl text-[13px] text-ink-2" data-testid="news-line">
      <span className="text-ink-3">{NEWS_NAME}:</span> Football only {l.football} · news {l.news}
      {l.why && <> ({l.why})</>}
    </p>
  )
}
