import type { LeagueFile, TeamFile, TeamsFile } from '../../data/contract'

/** M18.6. `league` and `file` are undefined when those files are missing: what needs them drops. */
export function Games(_: { code: string; teams: TeamsFile; league?: LeagueFile; file?: TeamFile }) {
  return null
}
