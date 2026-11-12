/** The 32 teams by conference and division: a copy of src/nfl/league/divisions.py for the browser engine (M26.3). */

export type Conf = 'AFC' | 'NFC'
export const CONFS: Conf[] = ['AFC', 'NFC']

/** In the Python dict's order: the tiebreak procedure walks divisions in this order. */
export const DIVISION_TEAMS: Record<string, readonly string[]> = {
  'AFC East': ['BUF', 'MIA', 'NE', 'NYJ'],
  'AFC North': ['BAL', 'CIN', 'CLE', 'PIT'],
  'AFC South': ['HOU', 'IND', 'JAX', 'TEN'],
  'AFC West': ['DEN', 'KC', 'LAC', 'LV'],
  'NFC East': ['DAL', 'NYG', 'PHI', 'WAS'],
  'NFC North': ['CHI', 'DET', 'GB', 'MIN'],
  'NFC South': ['ATL', 'CAR', 'NO', 'TB'],
  'NFC West': ['ARI', 'LA', 'SEA', 'SF'],
}

/** code -> [conference, division] */
export const DIVISIONS: Record<string, [Conf, string]> = Object.fromEntries(
  Object.entries(DIVISION_TEAMS).flatMap(([name, codes]) => codes.map((c) => [c, [name.split(' ')[0] as Conf, name]])),
)

/** Every team, sorted: the engine's team index order (Python's `sorted(DIVISIONS)`). */
export const TEAMS: string[] = Object.keys(DIVISIONS).sort()

export const DIVISION_SET: Record<string, Set<string>> = Object.fromEntries(TEAMS.map((t) => [t, new Set(DIVISION_TEAMS[DIVISIONS[t][1]])]))
export const CONFERENCE_SET: Record<Conf, Set<string>> = {
  AFC: new Set(TEAMS.filter((t) => DIVISIONS[t][0] === 'AFC')),
  NFC: new Set(TEAMS.filter((t) => DIVISIONS[t][0] === 'NFC')),
}
