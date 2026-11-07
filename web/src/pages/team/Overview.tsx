import type { LeagueFile, SimilarFile, TeamsFile } from '../../data/contract'

/** M18.3. `league` and `similar` are undefined when those files are missing: their sections drop. */
export function Overview(_: { code: string; teams: TeamsFile; league?: LeagueFile; similar?: SimilarFile }) {
  return null
}
