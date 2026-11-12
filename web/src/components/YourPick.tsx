/**
 * "Your pick" (M26.1, ADR 0029): two team buttons until kickoff, then the pick and how it did.
 * Used under each slate card (`size="card"`) and on the game page (`size="page"`). Needs a
 * `[data-matchup]` ancestor for the team colors (`--team-away`, `--team-home`).
 */
import type { CSSProperties } from 'react'
import type { GameRow } from '../data/contract'
import { pickOpen, setPick, usePicks } from '../lib/picks'
import { teamInfo } from '../lib/teams'

type Props = { g: Pick<GameRow, 'game_id' | 'home' | 'away' | 'kickoff_utc' | 'result'>; size?: 'card' | 'page'; now?: number }

const homeWon = (g: Props['g']): boolean | null => {
  const m = g.result?.margin
  return m == null || m === 0 ? null : m > 0
}

function TeamButton({ team, side, on, other, onClick, page }: { team: string; side: 'away' | 'home'; on: boolean; other: boolean; onClick: () => void; page: boolean }) {
  const c = `var(--team-${side})`
  const style = {
    '--pick-c': c,
    background: on ? `color-mix(in srgb, ${c} 30%, var(--surface-1))` : undefined,
    boxShadow: on ? `inset 0 0 0 2px ${c}` : undefined,
  } as CSSProperties
  return (
    <button
      type="button"
      aria-pressed={on}
      title={on ? `Clear your pick of ${teamInfo(team).name}` : `Pick ${teamInfo(team).name} to win`}
      onClick={onClick}
      style={style}
      className={[
        'pick-btn group relative inline-flex cursor-pointer items-center justify-center gap-1.5 rounded-md border font-semibold',
        'transition-[background-color,box-shadow,opacity,transform] duration-[var(--dur-fast)] ease-[var(--ease-out)]',
        'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] active:scale-[0.97]',
        page ? 'min-w-28 flex-1 flex-col px-4 py-2.5 text-lg sm:flex-none' : 'min-w-16 px-3 py-1 text-[13px]',
        on ? 'pick-pop border-transparent text-ink' : 'border-line text-ink-2 hover:text-ink',
        other ? 'opacity-55 hover:opacity-100' : '',
      ].join(' ')}
    >
      <span className="inline-flex items-center gap-1.5">
        <span aria-hidden className={`inline-block rounded-full ${page ? 'h-2.5 w-2.5' : 'h-2 w-2'}`} style={{ background: c }} />
        {team}
        {on && (
          <svg aria-hidden viewBox="0 0 16 16" className={page ? 'h-4 w-4' : 'h-3.5 w-3.5'} fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 8.5l3.2 3L13 4.5" />
          </svg>
        )}
      </span>
      {page && <span className="text-[12px] font-normal text-ink-2">{teamInfo(team).name}</span>}
    </button>
  )
}

export function YourPick({ g, size = 'card', now }: Props) {
  const picks = usePicks()
  const mine = picks[g.game_id]?.team ?? null
  const page = size === 'page'
  const wrap = page ? 'flex flex-col gap-2 rounded-lg border border-line bg-surface-1 p-3 sm:flex-row sm:items-center sm:gap-4' : 'flex items-center gap-2 border-t border-line px-3 py-2'

  if (!pickOpen(g, now)) {
    if (!mine) return page && g.result == null ? <div className={`${wrap} text-[13px] text-ink-3`}>Picks closed at kickoff.</div> : null
    const won = homeWon(g)
    const ok = won == null ? null : (mine === g.home) === won
    const side = mine === g.home ? 'home' : 'away'
    return (
      <div className={`${wrap} text-[13px] text-ink-2`}>
        <span className="inline-flex items-center gap-1.5">
          Your pick:
          <span className="inline-flex items-center gap-1 font-semibold text-ink">
            <span aria-hidden className="inline-block h-2 w-2 rounded-full" style={{ background: `var(--team-${side})` }} />
            {mine}
          </span>
        </span>
        {ok != null && (
          <span aria-label={ok ? 'right' : 'wrong'} title={ok ? 'Right' : 'Wrong'} className={`rounded-full px-1.5 text-[12px] font-medium ${ok ? 'bg-[color-mix(in_srgb,var(--good)_18%,transparent)] text-ink' : 'bg-surface-2 text-ink-3'}`}>
            {ok ? '✓ right' : '✗ wrong'}
          </span>
        )}
        {g.result == null && <span className="text-ink-3">· closed at kickoff</span>}
      </div>
    )
  }

  const btn = (team: string, side: 'away' | 'home') => (
    <TeamButton team={team} side={side} on={mine === team} other={mine != null && mine !== team} onClick={() => setPick(g, mine === team ? null : team)} page={page} />
  )
  return (
    <div role="group" aria-label={`Your pick: ${g.away} at ${g.home}`} className={wrap}>
      <span className={page ? 'flex flex-col' : 'mr-auto text-[13px] text-ink-2'}>
        {page ? (
          <>
            <span className="text-[15px] font-medium text-ink">{mine ? 'Your pick' : 'Who wins? Make your pick'}</span>
            <span className="text-[12px] text-ink-3">Saved in this browser; open until kickoff. Your record is on the slate.</span>
          </>
        ) : mine ? (
          'Your pick'
        ) : (
          'Who wins?'
        )}
      </span>
      <span className={page ? 'flex gap-2 sm:ml-auto' : 'flex gap-2'}>
        {btn(g.away, 'away')}
        {btn(g.home, 'home')}
      </span>
    </div>
  )
}
