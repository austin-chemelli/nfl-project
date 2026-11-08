import { Section } from '../../components/ui'
import type { Tracker } from '../../data/contract'

const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric', year: 'numeric' }) : null)
const plural = (n: number, one: string) => `${n} ${one}${n === 1 ? '' : 's'}`

/** The Student's total at live locks (ADR 0024): context beside the lines, never in the scorecard. */
export function Totals({ t }: { t: Tracker }) {
  const x = t.totals
  if (!x) return null
  return (
    <Section title="Totals, new" help="The Student's predicted combined score, locked with its line. It's context and a bit of fun: it never enters the scorecard above or the README.">
      <p className="m-0 text-ink-2">
        Tracked since {day(x.first_lock)}, {plural(x.weeks, 'week')}.{' '}
        {x.n === 0 || x.mae == null
          ? 'No locked game has finished yet.'
          : `${plural(x.n, 'game')} finished: the total missed by ${x.mae.toFixed(1)} points on average${x.market_mae != null ? `, the market's total at the lock by ${x.market_mae.toFixed(1)}` : ''}.`}
        {x.side_n > 0 && ` Its side of the market total was right ${x.side_right} of ${x.side_n}.`}
      </p>
      <p className="m-0 mt-2 text-[13px] text-ink-3">In the backtest the total trailed the market&apos;s closing total by a fraction of a point per game, and its side of that total was close to a coin flip.</p>
    </Section>
  )
}
