import type { TeamsFile } from '../../data/contract'

/** The Teams tab (M14.4 fills this in). */
export function Teams({ file }: { file: TeamsFile }) {
  return <p className="text-ink-2">{Object.keys(file.teams).length} teams, entering Week {file.week}.</p>
}
