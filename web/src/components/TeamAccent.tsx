import { teamInfo } from '../lib/teams'

/** A thin bar in the team's color (gray for unknown codes), or `color` inside a matchup. Decorative; the team name sits next to it. */
export function TeamAccent({ team, color, className = '' }: { team: string; color?: string; className?: string }) {
  // the ring keeps near-black colors (LV, PIT) visible in dark mode
  return <span aria-hidden data-team={team} className={`block h-[3px] w-full rounded-full ring-1 ring-[var(--border)] ${className}`} style={{ background: color ?? teamInfo(team).color }} />
}
