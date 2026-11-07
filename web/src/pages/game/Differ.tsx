import { ModelBadge, Section } from '../../components/ui'
import type { Game } from '../../data/contract'
import { WHY, factorLines, outcome, whatIfLine, whoText } from './differ'

/**
 * Where the approaches differ from the market, and what could swing the game (ADR 0024). The strong calls
 * were recorded at the lock with their reasons; the what-if is our model's own sensitivity to the
 * quarterback, rescored with the locked models. Nothing here is the market's view.
 */
export function Differ({ g }: { g: Game }) {
  const qbs = g.swings.filter((s) => s.kind === 'qb')
  const factors = factorLines(g.swings)
  if (g.strong_calls.length === 0 && qbs.length === 0 && factors.length === 0) return null
  return (
    <Section title="Where we differ from the market" help="A strong call is an approach 10 or more points of win chance away from the market at the lock, recorded with its reasons and graded after the game.">
      {g.strong_calls.length > 0 ? (
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {g.strong_calls.map((c) => (
            <li key={`${c.model_id}-${c.lock_ts}`} className="rounded-md border border-line bg-surface-1 p-2.5">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 text-[13px]">
                <ModelBadge modelId={c.model_id} />
                {outcome(c) && <span className={c.result === 'right' ? 'text-[var(--good)]' : c.result === 'wrong' ? 'text-[var(--critical)]' : 'text-ink-3'}>{outcome(c)}</span>}
              </div>
              <p className="m-0 mt-1 text-ink">{c.sentence}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="m-0 text-ink-2">No approach is 10 or more points from the market on this game.</p>
      )}
      {qbs.map((s) => {
        const line = whatIfLine(g, s)
        return line ? (
          <p key={s.team ?? ''} className="m-0 mt-3 text-ink">
            <span className="text-ink-2">Our line assumes {whoText(s.assumed)} starts for {s.team}, though {WHY[s.why ?? ''] ?? 'the starter is in doubt'}.</span> {line}
          </p>
        ) : null
      })}
      {factors.length > 0 && (
        <div className="mt-3">
          <h3 className="text-[13px] font-medium text-ink">Also worth watching</h3>
          <ul className="mt-1 list-disc pl-5 text-[13px] text-ink-2">
            {factors.map((f) => <li key={f}>{f}</li>)}
          </ul>
        </div>
      )}
    </Section>
  )
}

/** On a finished game: each strong call and how it turned out. */
export function StrongCallsOutcome({ g }: { g: Game }) {
  const done = g.strong_calls.filter((c) => c.result != null)
  if (done.length === 0) return null
  return (
    <Section title="Strong calls on this game">
      <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[14px]">
        {done.map((c) => (
          <li key={`${c.model_id}-${c.lock_ts}`} className="flex flex-wrap items-baseline gap-x-2">
            <ModelBadge modelId={c.model_id} />
            <span className="text-ink">had {c.team} at {Math.round(100 * (c.side === 'home' ? c.p_home : 1 - c.p_home))}% against the market&apos;s {Math.round(100 * (c.side === 'home' ? c.market_p : 1 - c.market_p))}%:</span>
            <span className={c.result === 'right' ? 'text-[var(--good)]' : c.result === 'wrong' ? 'text-[var(--critical)]' : 'text-ink-3'}>{outcome(c)}</span>
          </li>
        ))}
      </ul>
    </Section>
  )
}

