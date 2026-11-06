/** The eight starting pairs of the Teams tab (.notes/plans/team-scatter.md "Presets"). Captions: top left, top right, bottom left, bottom right. */
export type Quadrants = [string, string, string, string]

export type Preset = { id: string; chip: string; x: string; y: string; quadrants: Quadrants }

/** Axis direction (flip) is never stored here: it comes from `better` on the feature. */
export const PRESETS: Preset[] = [
  {
    id: 'offense-defense',
    chip: 'Offense vs defense',
    x: 'strength.epa_off',
    y: 'strength.epa_def',
    quadrants: ['Defense carries them', 'Good on both sides', 'Struggling both ways', 'Offense carries them'],
  },
  {
    id: 'pass-more',
    chip: 'Pass more, gain more?',
    x: 'decisions.pass_rate_oe',
    y: 'strength.success_off',
    quadrants: ['Run more, and it works', 'Pass more, and it works', 'Run more, without results', 'Pass more, without results'],
  },
  {
    id: 'luck-margin',
    chip: 'Luck vs margin',
    x: 'strength.point_diff_pg',
    y: 'strength.luck',
    quadrants: [
      'Winning more than their points say',
      'Good, and winning even more',
      'Struggling, and losing the close ones',
      'Good, but winning less than their points say',
    ],
  },
  {
    id: 'pass-rush-offense',
    chip: 'Passing vs rushing offense',
    x: 'strength.epa_pass_off',
    y: 'strength.epa_rush_off',
    quadrants: ['Run game carries it', 'Move it both ways', 'Stalled both ways', 'Passing carries it'],
  },
  {
    id: 'pass-rush-defense',
    chip: 'Pass vs run defense',
    x: 'strength.epa_pass_def',
    y: 'strength.epa_rush_def',
    quadrants: ['Stop the run only', 'Stop both', 'Stop neither', 'Stop the pass only'],
  },
  {
    id: 'rating-schedule',
    chip: 'Rating vs schedule',
    x: 'strength.elo_pre',
    y: 'strength.sos',
    quadrants: ['Weaker, hard schedule', 'Strong against a hard schedule', 'Weak, soft schedule', 'Strong, soft schedule so far'],
  },
  {
    id: 'the-lines',
    chip: 'The lines',
    x: 'strength.sack_rate_off',
    y: 'strength.sack_rate_def',
    quadrants: ['Pass rush only', 'Win both lines', 'Lose both lines', 'Protection only'],
  },
  {
    id: 'hot-or-not',
    chip: 'Hot or not',
    x: 'strength.point_diff_pg',
    y: 'form.epa_trend',
    quadrants: ['Improving from a weak start', 'Good and getting better', 'Weak and slipping', 'Good but slipping'],
  },
]

/** Preset 1 is the default. */
export const DEFAULT_PRESET = PRESETS[0]

export function presetFor(x: string, y: string): Preset | undefined {
  return PRESETS.find((p) => p.x === x && p.y === y)
}
