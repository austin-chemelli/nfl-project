import { teamInfo } from '../lib/teams'

/** A thin bar in the team's primary color (gray for unknown codes). Decorative; the team name sits next to it. */
export function TeamAccent({ team, className = '' }: { team: string; className?: string }) {
  // the ring keeps near-black colors (LV, PIT) visible in dark mode
  return <span aria-hidden data-team={team} className={`block h-[3px] w-full rounded-full ring-1 ring-[var(--border)] ${className}`} style={{ background: teamInfo(team).color }} />
}
