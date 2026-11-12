/** "Your pick" on a matchup card (M26.1): two team buttons until kickoff, then the pick and how it did. */
import type { GameRow } from '../../data/contract'
import { pickOpen, setPick, usePicks } from '../../lib/picks'
import { teamInfo } from '../../lib/teams'
import { homeWon } from './helpers'

export function PickRow({ g, now }: { g: GameRow; now?: number }) {
  const picks = usePicks()
  const mine = picks[g.game_id]?.team ?? null
  const open = pickOpen(g, now)
  if (!open) {
    if (!mine) return null
    const won = homeWon(g)
    const ok = won == null ? null : (mine === g.home) === won
    return (
      <div className="flex items-center gap-2 border-t border-line px-3 py-2 text-[13px] text-ink-2">
        <span>
          Your pick: <span className="font-medium text-ink">{mine}</span>
        </span>
        {ok != null && <span aria-label={ok ? 'right' : 'wrong'} title={ok ? 'Right' : 'Wrong'}>{ok ? '✓' : '✗'}</span>}
        {g.result == null && <span className="text-ink-3">· closed at kickoff</span>}
      </div>
    )
  }
  const btn = (team: string, side: 'away' | 'home') => {
    const on = mine === team
    return (
      <button
        type="button"
        aria-pressed={on}
        title={on ? `Clear your pick of ${teamInfo(team).name}` : `Pick ${teamInfo(team).name} to win`}
        onClick={() => setPick(g, on ? null : team)}
        className={`min-w-14 rounded-md border px-3 py-1 text-[13px] font-medium ${on ? 'border-transparent text-ink' : 'border-line text-ink-2 hover:bg-surface-2 hover:text-ink'}`}
        style={on ? { background: `color-mix(in srgb, var(--team-${side}) 30%, transparent)`, boxShadow: `inset 0 0 0 1.5px var(--team-${side})` } : undefined}
      >
        {team}
      </button>
    )
  }
  return (
    <div role="group" aria-label={`Your pick: ${g.away} at ${g.home}`} className="flex items-center gap-2 border-t border-line px-3 py-2">
      <span className="mr-auto text-[13px] text-ink-2">{mine ? 'Your pick' : 'Who wins?'}</span>
      {btn(g.away, 'away')}
      {btn(g.home, 'home')}
    </div>
  )
}
