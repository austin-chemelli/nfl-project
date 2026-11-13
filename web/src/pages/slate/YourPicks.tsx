/**
 * Your picks this season (M26.1): this week's progress and your record against the Student and the
 * market's favorite on the same games. Everything is read from this browser's picks and the slates.
 */
import { Help } from '../../components/Help'
import { useSlates } from '../../data/api'
import type { GameRow } from '../../data/contract'
import { HEADLINE, SHORT } from '../../lib/models'
import { clearOpenPicks, pickOpen, pickedWeeks, scorePicks, usePicks, type Tally } from '../../lib/picks'

const rec = (t: Tally) => `${t.w}–${t.l}`

export function YourPicks({ season, games, now }: { season: number; games: GameRow[]; now?: number }) {
  const picks = usePicks()
  const weeks = pickedWeeks(picks, season)
  const qs = useSlates(season, weeks)
  const open = games.filter((g) => pickOpen(g, now))
  const pickedOpen = open.filter((g) => picks[g.game_id]).length
  if (weeks.length === 0 && open.length === 0) return null

  const all = qs.flatMap((q) => q.data?.games ?? [])
  const r = scorePicks(picks, all, HEADLINE)
  const model = SHORT[HEADLINE] ?? HEADLINE
  return (
    <section aria-label="Your picks" className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-line bg-surface-1 px-3 py-2 text-[13px] text-ink-2">
      <span className="font-medium text-ink">
        Your picks{' '}
        <Help text="Pick the winner of any game until kickoff with the buttons on each card. Picks stay in this browser only: nothing is sent anywhere, and another device or a cleared browser starts empty. Your record counts only finished games you picked, and puts the Student and the market's favorite on those same games." />
      </span>
      {open.length > 0 && (
        <span>
          {pickedOpen} of {open.length} open games picked
        </span>
      )}
      {r.games > 0 ? (
        <span className="tabular">
          Season: you <b className="text-ink">{rec(r.you)}</b> · {model} {rec(r.model)} · market {rec(r.market)}
        </span>
      ) : (
        weeks.length > 0 && <span className="text-ink-3">Your record starts when a game you picked is final.</span>
      )}
      {pickedOpen > 0 && (
        <button type="button" onClick={() => clearOpenPicks(games, now)} className="ml-auto text-accent hover:underline">
          Clear this week's open picks
        </button>
      )}
    </section>
  )
}
