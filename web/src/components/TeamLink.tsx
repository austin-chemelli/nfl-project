import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { canonicalTeam, isTeam, teamInfo } from '../lib/teams'

/** A team's code or name, linking to its team page (ADR 0022). An unknown code stays plain text. */
export function TeamLink({ team, children, className }: { team: string; children?: ReactNode; className?: string }) {
  if (!isTeam(team)) return <>{children ?? team}</>
  return (
    <Link to={`/team/${canonicalTeam(team)}`} className={className} title={`${teamInfo(team).name}: team page`}>
      {children ?? team}
    </Link>
  )
}
