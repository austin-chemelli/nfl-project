import { FinePrint } from '../../components/FinePrint'
import type { NewsEffect as NewsEffectT } from '../../data/contract'
import { newsEffectText } from './newsEffect'

/** "What the news added": the Student against its football-only twin over live games (ADR 0032). */
export function NewsEffect({ e }: { e: NewsEffectT | null }) {
  if (!e) return null
  const t = newsEffectText(e)
  return (
    <div className="mt-6" data-testid="news-effect">
      <h3 className="m-0 text-[15px] font-semibold">What the news added</h3>
      <p className="mb-0 mt-1 max-w-3xl text-[13px] text-ink-2">{t.lede}</p>
      <p className="m-0 mt-1 max-w-3xl text-[13px] text-ink-2">{t.verdict}</p>
      <FinePrint label="How the news is counted">
        <p>The weights are declared, not learned: each is sized from what the same kind of news is worth on the depth chart, and the total is capped at 1.5 points a game. News can&apos;t be backtested, so it is judged live against a twin of the Student that never sees it.</p>
      </FinePrint>
    </div>
  )
}
