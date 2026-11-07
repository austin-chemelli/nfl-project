/**
 * The site JSON contract (mirrors src/nfl/site.py, schema v2). zod schemas validate every file at
 * load time so a Python-side contract change fails loudly (in tests and in dev) instead of rendering
 * blanks. Objects are "loose": extra fields are allowed, missing required ones are errors.
 */
import { z } from 'zod'

// zod's JIT probes `new Function`, which the site's CSP (no unsafe-eval) reports on every load.
z.config({ jitless: true })

const num = z.number()
const nnum = z.number().nullable()
const nstr = z.string().nullable()

// ---------------------------------------------------------------------------------------- meta

export const ModelInfo = z.looseObject({
  label: z.string(),
  kind: z.string(), // approach | reference | ensemble | global (the ensemble never reaches a page)
  approach: z.string().optional(),
})

export const Member = z.looseObject({
  feature: z.string(),
  sign: num,
  adv: z.boolean(),
  label: z.string(),
  unit: z.string(),
  description: z.string(),
})

export const Group = z.looseObject({
  id: z.string(),
  name: z.string(),
  heading: z.string(),
  meaning: z.string(),
  description: z.string(),
  game_level: z.boolean(),
  context_only: z.boolean().default(false), // shown as context, carries no weight in a public line
  members: z.array(Member),
})

export const Approach = z.looseObject({
  id: z.string(),
  name: z.string(),
  blurb: z.string(),
  emphasis: z.array(z.string()),
  public_line: z.string(),
  home_field_why: z.string(),
  why: z.record(z.string(), z.string()),
  persona_share: z.record(z.string(), num),
  public_share: z.record(z.string(), num),
  history_share: z.record(z.string(), num),
  history_shifted_points: nnum,
  calibration_scale: nnum,
  trained_through: num,
})

export const TendencyMetric = z.looseObject({
  side: z.enum(['off', 'def']),
  label: z.string(),
  unit: z.string(),
  pair: nstr,
  help: z.string(),
})

export const Meta = z.looseObject({
  schema_version: z.string(),
  generated_at: z.string(),
  season: num,
  current_week: num,
  weeks: z.array(num),
  freshness: z.record(z.string(), z.string()),
  models: z.record(z.string(), ModelInfo),
  approaches: z.array(Approach),
  groups: z.looseObject({
    registry_version: z.string(),
    headings: z.array(z.string()),
    units: z.record(z.string(), z.string()),
    groups: z.array(Group),
  }),
  // added in site.py after the first publish; older meta.json files lack them (labels fall back to ids)
  tendency_metrics: z.record(z.string(), TendencyMetric).default({}),
  tendency_situations: z.record(z.string(), z.string()).default({}),
  // the league's spread per team-level feature (Details tab); older files lack it and the rows go plain
  feature_bands: z.record(z.string(), z.looseObject({ lo: num, q1: num, med: num, q3: num, hi: num })).default({}),
  last_lock: z.looseObject({ lock_ts: z.string(), season: num, week: num, slot: nstr }).nullable(),
})

// --------------------------------------------------------------------------------------- slate

export const ModelPick = z.looseObject({
  p_home: num,
  spread_home: nnum,
  status: z.enum(['locked', 'backfill', 'preview', 'pregame']),
  lock_ts: nstr,
  divergence: nnum,
})

export const MarketLine = z.looseObject({
  p_home: nnum,
  spread_home: nnum,
  total: nnum,
  as_of: nstr,
  source: nstr,
})

const qbSides = z.looseObject({ home: nstr.default(null), away: nstr.default(null) }).default({ home: null, away: null })

/** What a slate card needs beyond the row (U4). Absent from files built before it, so the whole block is optional. */
export const CardData = z.looseObject({
  edges: z.record(z.string(), z.looseObject({ favors: nstr, strength_pct: nnum })).default({}),
  injuries: z
    .array(z.looseObject({ team: z.string(), player: z.string(), pos: nstr, status: z.string(), starter: z.boolean().default(false), new: z.boolean().default(false) }))
    .default([]),
  usual_qb: qbSides,
  last_qb: qbSides,
  charted_qb: qbSides,
  weather_concern: nnum.default(null),
  contrast: z
    .looseObject({ offense: z.string(), defense: z.string(), off_label: z.string(), def_label: z.string(), off_rank: num, def_rank: num })
    .nullable()
    .default(null),
})

export const GameRow = z.looseObject({
  game_id: z.string(),
  season: num,
  week: num,
  kickoff_utc: z.string(),
  away: z.string(),
  home: z.string(),
  stadium: nstr,
  roof: nstr,
  neutral_site: z.boolean(),
  away_qb: nstr,
  home_qb: nstr,
  result: z.looseObject({ home_score: nnum, away_score: nnum, margin: num }).nullable(),
  market: MarketLine.nullable(),
  models: z.record(z.string(), ModelPick),
  // a bad card costs that game its why line, not the week its slate; contract.test.ts checks them
  card: CardData.nullable().default(null).catch((ctx) => {
    console.warn('slate card dropped', ctx.error.issues.slice(0, 3))
    return null
  }),
})

export const Slate = z.looseObject({
  schema_version: z.string(),
  season: num,
  week: num,
  generated_at: z.string(),
  games: z.array(GameRow),
})

// ---------------------------------------------------------------------------------------- game

export const Contribution = z.looseObject({
  p_home: num,
  home_field_pp: nnum,
  groups: z.record(z.string(), z.looseObject({ pp: nnum, features: z.record(z.string(), nnum) })),
})

export const Tendency = z.looseObject({
  team_side: z.enum(['home', 'away']),
  side: z.enum(['off', 'def']),
  situation: z.string(),
  metric: z.string(),
  rate: nnum,
  raw_rate: nnum,
  n: num,
  league_rate: nnum,
})

export const Injury = z.looseObject({
  week: num,
  team: z.string(),
  player: z.string(),
  pos: nstr,
  status: z.string(),
  practice: nstr,
  injury: nstr,
})

const Url = z.string()
export const Note = z.looseObject({ text: z.string(), kind: z.string(), impact: num, source_url: Url.nullable() })
export const SchemeTrend = z.looseObject({
  unit: z.enum(['offense', 'defense']),
  trend: z.string(),
  working: z.boolean().nullable(),
  sources: z.array(Url),
})
export const TeamNarrative = z.looseObject({
  team: z.string(),
  qb_status: num,
  qb_name: nstr,
  injury_impact: num,
  key_absences: z.array(z.string()),
  sentiment: num,
  hype: num,
  coaching_turmoil: num,
  motivation: num,
  revenge: z.boolean(),
  lookahead: z.boolean(),
  summary: z.string(),
  notes: z.array(Note).default([]),
  scheme_trends: z.array(SchemeTrend).default([]),
})
export const Narrative = z.looseObject({
  schema_version: z.string(),
  game_id: z.string(),
  known_as_of: z.string(),
  producer: z.string(),
  model: z.string(),
  home: TeamNarrative,
  away: TeamNarrative,
  public_pick: nstr.optional(),
  public_bet_pct_home: nnum.optional(),
  upset_buzz: num,
  weather_concern: num,
  consensus_narrative: z.string(),
  matchup_notes: z.array(z.looseObject({ text: z.string(), support: num, sources: z.array(Url) })).default([]),
  claims: z.array(
    z.looseObject({
      claim: z.string(),
      category: z.string(),
      team: nstr.optional(),
      source_url: Url,
      source_title: nstr.optional(),
      published_at: nstr.optional(),
      confidence: z.string(),
    }),
  ),
})

export const Game = GameRow.extend({
  contributions: z.record(z.string(), Contribution),
  edges: z.record(z.string(), z.looseObject({ favors: nstr, strength_pct: nnum })),
  features: z.record(z.string(), z.looseObject({ group: nstr, home: nnum.optional(), away: nnum.optional(), game: nnum.optional() })),
  tendencies: z.array(Tendency),
  injuries: z.array(Injury),
  narrative: Narrative.nullable(),
})

// --------------------------------------------------------------------------- retrospective
// Mirrors src/nfl/retro/schema.py (ADR 0016). Separate files (site/retro/<id>.json,
// site/recap_<season>_<ww>.json); a 404 means not built yet. Swing points are from the named team's
// view (positive = helped it); pp is toward home; value is the drop-one log-loss change.

const RetroKind = z.enum(['approach', 'ensemble', 'reference', 'global'])

export const Efficiency = z.looseObject({
  metric: z.string(),
  unit_side: z.enum(['off', 'def']),
  label: z.string(),
  unit: z.string(),
  higher_is_better: z.boolean(),
  game: nnum,
  season: nnum,
  league: nnum,
  league_lo: nnum.default(null),
  league_hi: nnum.default(null),
  season_games: num,
})

export const LuckFactor = z.looseObject({
  factor: z.string(),
  label: z.string(),
  actual: num,
  expected: num,
  unit: z.string(),
  attempts: nnum,
  swing_pts: num,
  partly_skill: z.boolean().default(false),
  sentence: z.string(),
})

export const TeamRetro = z.looseObject({
  team: z.string(),
  score: num,
  efficiency: z.array(Efficiency),
  luck: z.array(LuckFactor),
  luck_net: num,
})

export const GradedPick = z.looseObject({
  model_id: z.string(),
  label: z.string(),
  kind: RetroKind,
  status: z.string(),
  p_home: num,
  pick: z.string(),
  p_pick: num,
  right: z.boolean().nullable(),
  log_loss: num,
  spread_home: nnum,
  spread_error: nnum,
  best: z.boolean(),
})

export const GroupValue = z.looseObject({ group: z.string(), label: z.string(), pp: num, value: num })

export const Attribution = z.looseObject({
  model_id: z.string(),
  label: z.string(),
  groups: z.array(GroupValue),
  most_valuable: nstr,
})

export const Phase = z.looseObject({
  phase: z.string(), label: z.string(), note: z.string(), home: nnum, away: nnum,
  home_text: z.string(), away_text: z.string(), leader: z.enum(['home', 'away']).nullable(),
})

export const WpPlay = z.looseObject({
  play_id: num,
  t: num,
  qtr: num,
  clock: z.string(),
  team: nstr,
  p_before: num,
  p_after: num,
  wpa: num,
  factor: nstr,
  text: z.string(),
})

const WpPoint = z.tuple([num, num])

export const WpSeries = z.looseObject({
  model: z.string(),
  points: z.array(WpPoint),
  end_t: num,
  ot: z.boolean(),
  plays: z.array(WpPlay),
  winner_low: WpPoint.nullable(),
})

export const Drive = z.looseObject({
  n: num,
  team: z.string(),
  qtr: num,
  t0: num,
  t1: num,
  start_yl: nnum,
  end_yl: nnum,
  plays: nnum,
  result: nstr,
})

export const RetroGame = z.looseObject({
  schema_version: z.string(),
  game_id: z.string(),
  season: num,
  week: num,
  kickoff_utc: z.string(),
  away: z.string(),
  home: z.string(),
  result: z.looseObject({ home_score: num, away_score: num, margin: num }),
  built_at: z.string(),
  pbp_snapshot_ts: z.string(),
  expectations_version: z.string(),
  headlines: z.array(z.string()),
  played_like: z.looseObject({
    p_home: num, favored: z.string(), matches_result: z.boolean().nullable(), sentence: z.string(),
    // what went in; retros from before schema 3 lack them
    home_epa: nnum.default(null), away_epa: nnum.default(null), home_success: nnum.default(null), away_success: nnum.default(null), p_base: nnum.default(null),
  }),
  phases: z.array(Phase).default([]), // retros from before schema 3 lack it
  teams: z.looseObject({ home: TeamRetro, away: TeamRetro }),
  predictions: z.array(GradedPick),
  best_model: nstr,
  attribution: z.array(Attribution),
  wp_series: WpSeries.nullish(), // retros from before schema 6 lack both
  drives: z.array(Drive).nullish(),
})

export const RecapModel = z.looseObject({
  model_id: z.string(),
  label: z.string(),
  kind: RetroKind,
  n: num,
  right: num,
  log_loss: num,
  vs_market: nnum,
  rank: num,
})

const RecapGame = z.looseObject({ game_id: z.string(), away: z.string(), home: z.string(), value: num, sentence: z.string() })
const BoldCall = z.looseObject({
  game_id: z.string(), away: z.string(), home: z.string(), model_id: z.string(), label: z.string(), pick: z.string(),
  p_pick: num, log_loss: num, earned: num, sentence: z.string(),
})
const RecapTeam = z.looseObject({ team: z.string(), game_id: z.string(), luck_net: num, sentence: z.string() })

export const WeekRecap = z.looseObject({
  schema_version: z.string(),
  season: num,
  week: num,
  built_at: z.string(),
  games: z.array(z.string()),
  best_model: nstr,
  models: z.array(RecapModel),
  upsets: z.array(RecapGame),
  misread: z.array(RecapGame),
  luckiest: z.array(RecapTeam),
  unluckiest: z.array(RecapTeam),
  note: z.string(),
  best_call: BoldCall.nullable().default(null),
  costliest_call: BoldCall.nullable().default(null),
})

// ------------------------------------------------------------------------------------- tracker

export const Tracker = z.looseObject({
  schema_version: z.string(),
  season: num,
  seasons: z.array(z.looseObject({ season: num, model_id: z.string(), n: num, log_loss: num, brier: num, ece: nnum, spread_mae: nnum })),
  current_season: z.array(z.looseObject({ model_id: z.string(), week: num, n: num, n_live: num.optional(), cum_log_loss: num, live: z.boolean() })),
  weeks_tracked: z.record(z.string(), num),
  backtest: z.array(
    z.looseObject({
      model_id: z.string(), seasons: num, first_season: num, last_season: num, n_games: num,
      log_loss: num, ll_lo: num, ll_hi: num, d_vs_market: nnum, d_lo: nnum, d_hi: nnum,
    }),
  ),
  reliability: z.array(z.looseObject({ model_id: z.string(), bin: num, n: num, mean_p: num, hit_rate: num })),
  divergence: z.array(
    z.looseObject({
      model_id: z.string(), bucket: z.string(), n: num, lean_win_rate: nnum, market_expected_rate: nnum,
      model_log_loss: nnum, market_log_loss: nnum,
    }),
  ),
  ledger: z.array(
    z.looseObject({
      model_id: z.string(), kind: z.string(), bets: num, wins: num, losses: num, pushes: num,
      units: nnum, roi: nnum, clv: nnum,
      roi_lo: nnum.optional(), roi_hi: nnum.optional(), no_edge_roi: nnum.optional(),
      win_rate: nnum.optional(), need_rate: nnum.optional(),
    }),
  ),
  ledger_seasons: z.array(
    z.looseObject({ model_id: z.string(), season: num, bets: num, live_bets: num, units: num, no_edge_units: num }),
  ).optional(),
})

// --------------------------------------------------------------------------------- hypotheses

export const SeasonPoint = z.looseObject({
  season: num, n_games: num, n_edge: num, edge_wins: num.optional(), edge_win_rate: nnum,
  improvement: nnum, skill_pct: nnum,
})
export const Hypotheses = z.looseObject({
  schema_version: z.string(),
  generated_at: z.string(),
  trained_seasons: z.array(num),
  n_games: num,
  features: z.array(
    z.looseObject({
      feature: z.string(), label: z.string(), group: nstr, verdict: z.string(), description: nstr.optional(),
      unit: nstr.optional(), effect_pp: num, effect_lo_pp: num, effect_hi_pp: num, marginal_pp: num,
      sentence: z.string(), coverage: z.string(), first_season: nnum.optional(), share_nonnull: nnum.optional(),
      personas: z.array(z.looseObject({ id: z.string(), name: z.string(), w: num })),
    }),
  ),
  by_season: z.looseObject({
    first_scored: num,
    items: z.record(
      z.string(),
      z.looseObject({
        kind: z.string(), label: z.string(), description: nstr.optional(), unit: nstr.optional(), group: nstr.optional(),
        pooled: z.looseObject({
          n_games: num, edge_win_rate: nnum, improvement: nnum, skill_pct: nnum.optional(),
          best_season: nnum.optional(), worst_season: nnum.optional(),
        }),
        series: z.array(SeasonPoint),
        sentence: z.string(),
      }),
    ),
  }),
})

// ------------------------------------------------------------------------------------ coaches

const MetricSummary = z.looseObject({ pct: nnum, dev: nnum, spread: nnum, seasons: num })
export const CoachSummary = z.looseObject({
  n_seasons: num,
  first_season: nnum,
  last_season: nnum,
  teams: z.array(z.string()),
  n_teams: num,
  spread: nnum,
  consistency: nstr, // "very consistent" | "fairly consistent" | "changes a lot"
  target: num,
  history: z.string(),
  sentence: z.string().optional(),
  metrics: z.record(z.string(), MetricSummary),
})
export const CoachSeason = z.looseObject({
  season: num,
  team: z.string(),
  source: z.string(),
  partial: z.boolean(),
  qb: z.looseObject({ name: z.string(), dropbacks: num, epa: nnum }).nullable(),
  metrics: z.record(z.string(), z.looseObject({ rate: nnum, pct: nnum, n: num, league: nnum })),
})
export const CoachSide = z.looseObject({
  side: z.enum(['off', 'def']),
  role: z.string(),
  seasons: z.array(CoachSeason),
  summary: CoachSummary.nullable(),
})
export const TeamCaller = z.looseObject({
  name: z.string(),
  source: z.string(),
  is_head_coach: z.boolean(),
  has_history: z.boolean(),
  prior: CoachSummary.nullable().optional(),
  sentence: z.string(),
})
export const Coaches = z.looseObject({
  generated_at: z.string(),
  current_season: num,
  decay: num.optional(),
  metrics: z.record(
    z.string(),
    z.looseObject({
      side: z.enum(['off', 'def']), label: z.string(), kind: z.string(), noun: z.string(),
      hi: z.string(), lo: z.string(), help: z.string(), unit: z.string(),
    }),
  ),
  consistency_thresholds: z.looseObject({ very: num, fairly: num }),
  note: z.string(),
  people: z.array(z.looseObject({ name: z.string(), sides: z.array(CoachSide) })),
  teams: z.record(
    z.string(),
    z.looseObject({ head_coach: nstr, team_printed: nstr.optional(), off: TeamCaller.nullable(), def: TeamCaller.nullable() }),
  ),
  /** season -> side -> metric -> league rate */
  league: z.record(z.string(), z.record(z.string(), z.record(z.string(), nnum))),
})

// ------------------------------------------------------------------------------ diy and season

export const DiyMatrix = z.looseObject({
  version: num,
  groups: z.array(z.string()),
  inactive: z.array(z.string()),
  first_scored: num,
  n: num,
  columns: z.looseObject({
    game_id: z.array(z.string()), season: z.array(num), week: z.array(num), y: z.array(num),
    warmup: z.array(z.union([num, z.boolean()])), mkt_p: z.array(nnum),
  }),
  c: z.record(z.string(), z.array(num)),
  personas: z.record(z.string(), z.looseObject({ name: z.string(), intercept: num, W: z.record(z.string(), num) })),
  student_fitted: z.record(z.string(), z.looseObject({ intercept: num, W: z.record(z.string(), num) })),
})

export const SeasonFile = z.looseObject({
  version: num,
  season: num,
  groups: z.array(z.string()),
  n: num,
  game_id: z.array(z.string()),
  week: z.array(num),
  home: z.array(z.string()),
  away: z.array(z.string()),
  kickoff: z.array(nstr),
  result: z.array(nnum),
  home_won: z.array(num),
  market_p: z.array(nnum),
  c: z.record(z.string(), z.array(num)),
})

export const Audit = z.looseObject({
  schema_version: z.string(),
  freshness: z.record(z.string(), z.string()),
  null_rates: z
    .array(z.looseObject({ tbl: z.string(), season: num, col: z.string(), n_rows: num, n_null: num, null_rate: num }))
    .optional(),
})

export type Meta = z.infer<typeof Meta>
export type Approach = z.infer<typeof Approach>
export type Group = z.infer<typeof Group>
export type Member = z.infer<typeof Member>
export type Slate = z.infer<typeof Slate>
export type CardData = z.infer<typeof CardData>
export type GameRow = z.infer<typeof GameRow>
export type ModelPick = z.infer<typeof ModelPick>
export type Game = z.infer<typeof Game>
export type Contribution = z.infer<typeof Contribution>
export type Tendency = z.infer<typeof Tendency>
export type Narrative = z.infer<typeof Narrative>
export type Tracker = z.infer<typeof Tracker>
export type Hypotheses = z.infer<typeof Hypotheses>
export type Coaches = z.infer<typeof Coaches>
export type CoachSide = z.infer<typeof CoachSide>
export type CoachSummary = z.infer<typeof CoachSummary>
export type TeamCaller = z.infer<typeof TeamCaller>
export type DiyMatrix = z.infer<typeof DiyMatrix>
export type SeasonFile = z.infer<typeof SeasonFile>
export type Audit = z.infer<typeof Audit>
export type RetroGame = z.infer<typeof RetroGame>
export type WpSeries = z.infer<typeof WpSeries>
export type WpPlay = z.infer<typeof WpPlay>
export type Drive = z.infer<typeof Drive>
export type TeamRetro = z.infer<typeof TeamRetro>
// ---------------------------------------------------------------------------------- teams (ADR 0019)

export const TeamFeature = z.looseObject({
  id: z.string(),
  label: z.string(),
  short: z.string(), // axis label, at most 22 characters
  description: z.string(),
  unit: z.string(),
  group: z.string(),
  group_name: z.string(),
  better: z.enum(['higher', 'lower']).nullable(), // null: a style or neutral measure, no good or bad
  n: num,
  mean: num,
  lo: num,
  q1: num,
  med: num,
  q3: num,
  hi: num,
})

export const TeamGame = z.looseObject({
  id: z.string(),
  week: num,
  opp: z.string(),
  home: z.boolean(),
  pf: nnum, // null until played
  pa: nnum,
})

export const TeamRow = z.looseObject({
  conference: z.string(),
  division: z.string(),
  wins: num,
  losses: num,
  ties: num,
  games_played: num,
  points_for: num.default(0),
  points_against: num.default(0),
  through_week: nnum.default(null), // the week of the latest result in the record
  last_game_id: nstr.default(null),
  next_game_id: nstr.default(null),
  games: z.array(TeamGame).default([]),
  values: z.record(z.string(), num), // a missing value is an absent key
  pct: z.record(z.string(), num).optional(), // 0-100 by raw value, 100 = highest value
  rank: z.record(z.string(), num).optional(), // 1 = best by `better`; 1 = highest when better is null
})

export const TeamsFile = z.looseObject({
  schema_version: z.string(),
  generated_at: z.string(),
  season: num,
  week: num,
  as_of: z.string(),
  features: z.array(TeamFeature),
  teams: z.record(z.string(), TeamRow),
})

export type Efficiency = z.infer<typeof Efficiency>
export type LuckFactor = z.infer<typeof LuckFactor>
export type GradedPick = z.infer<typeof GradedPick>
export type Attribution = z.infer<typeof Attribution>
export type WeekRecap = z.infer<typeof WeekRecap>
export type TeamFeature = z.infer<typeof TeamFeature>
export type TeamGame = z.infer<typeof TeamGame>
export type TeamRow = z.infer<typeof TeamRow>
export type TeamsFile = z.infer<typeof TeamsFile>

// ------------------------------------------------------------------------------------- league

/** One team's standing today (ADR 0019). `seed_today` is null outside the top seven of its conference. */
export const LeagueTeam = z.looseObject({
  team: z.string(),
  conf: z.string(),
  div: z.string(),
  w: num,
  l: num,
  t: num.default(0),
  pct: num,
  div_rec: z.string(),
  conf_rec: z.string(),
  pf: num,
  pa: num,
  left: num,
  div_rank: num,
  seed_today: nnum.default(null),
})

export const LeagueOddsTeam = z.looseObject({
  playoffs: num,
  division: num,
  bye: num,
  seed: z.array(num), // P(seed k), seven numbers
  rounds: z.looseObject({ div: num, conf: num, sb: num, champ: num }),
  wins: z.looseObject({ mean: num, lo: num, hi: num }), // lo and hi are the p10 and p90
})

/** One variant (the Student or the market). `sources` keys vary by variant, so it is a record of counts. */
export const LeagueVariant = z.looseObject({
  sources: z.record(z.string(), num).default({}),
  teams: z.record(z.string(), LeagueOddsTeam),
})

export const LeagueSwing = z.looseObject({ team: z.string(), if_home_win: num, if_away_win: num })

/** A remaining game. Swings come from the Student runs and only list teams past the reporting thresholds. */
export const LeagueGame = z.looseObject({
  game_id: z.string(),
  week: num,
  kickoff: nstr.default(null),
  home: z.string(),
  away: z.string(),
  p_student: nnum.default(null),
  p_market: nnum.default(null),
  market_source: nstr.default(null),
  leverage_total: num.default(0),
  swings: z.array(LeagueSwing).default([]),
  n_home_wins: num.default(0), // Student runs on each branch
  n_away_wins: num.default(0),
})

export const LeagueHistoryPoint = z.looseObject({ week: num, student: nnum.default(null), market: nnum.default(null) })

/** The furthest round a past team reached: wc, div, conf, sb, champ, or null. */
export const SimilarNeighbour = z.looseObject({
  season: num,
  team: z.string(), // as printed then (SD, OAK, STL)
  dist: num,
  rec_then: z.string(), // "6-2"
  final: z.string(), // "7-9-0"
  playoffs: z.boolean(),
  round: nstr.default(null),
  profile: z.array(num).default([]), // percentile by `measures` order
  closest: z.array(z.string()).default([]), // measure ids
  furthest: z.array(z.string()).default([]),
})

/** One flag from the fixed list of measures (docs: .notes/plans/similar-insights.md). `flagged` and `others` are [hits, n]. */
export const SimilarFlag = z.looseObject({
  kind: z.enum(['red', 'strength', 'fine']),
  measure: z.string(),
  label: z.string(),
  rank: num,
  quarter: z.enum(['bottom', 'top']),
  outcome: z.enum(['made', 'conf']),
  peers: z.string(), // "5-2"
  flagged: z.tuple([num, num]),
  others: z.tuple([num, num]),
})

/** What the nearest team-seasons did (descriptive, ADR 0019). `rounds` count reaching that round or beyond, of the `k_summary` nearest. */
export const SimilarTeam = z.looseObject({
  games_played: num,
  record: z.string().default(''),
  k_summary: num,
  made_playoffs: num,
  rounds: z.looseObject({ div: num, conf: num, sb: num, champ: num }),
  profile: z.array(num).default([]),
  pool: z.looseObject({ seasons: z.tuple([num, num]), n: num }).optional(),
  peers: z.looseObject({ made: num, n: num }).nullable().default(null), // everyone on exactly this record
  nearest: z.array(SimilarNeighbour).default([]),
  flags: z.array(SimilarFlag).default([]),
})

/** site/similar.json: its own file, read only by the Similar seasons tab. */
export const SimilarFile = z.looseObject({
  schema_version: z.string(),
  season: num,
  as_of: z.string(),
  measures: z.array(z.looseObject({ id: z.string(), label: z.string() })),
  teams: z.record(z.string(), SimilarTeam).default({}), // a team under four games has no entry
})

export const LeagueFile = z.looseObject({
  schema_version: z.string(),
  season: num,
  generated_at: z.string(),
  as_of: z.string(),
  through_week: nnum.default(null),
  n_sims: num,
  seed: num.optional(),
  shock_sigma: num,
  tiebreak: z.string().optional(),
  teams: z.array(LeagueTeam),
  odds: z.looseObject({ student: LeagueVariant, market: LeagueVariant }),
  games: z.array(LeagueGame).default([]),
  history: z.record(z.string(), z.array(LeagueHistoryPoint)).default({}),
})

export type LeagueTeam = z.infer<typeof LeagueTeam>
export type LeagueOddsTeam = z.infer<typeof LeagueOddsTeam>
export type LeagueVariant = z.infer<typeof LeagueVariant>
export type LeagueSwing = z.infer<typeof LeagueSwing>
export type LeagueGame = z.infer<typeof LeagueGame>
export type SimilarNeighbour = z.infer<typeof SimilarNeighbour>
export type SimilarTeam = z.infer<typeof SimilarTeam>
export type SimilarFlag = z.infer<typeof SimilarFlag>
export type SimilarFile = z.infer<typeof SimilarFile>
export type LeagueHistoryPoint = z.infer<typeof LeagueHistoryPoint>
export type LeagueFile = z.infer<typeof LeagueFile>

/** `site/team/<code>.json` (ADR 0021, 0022): one team's staff, evidence and tendencies. */
const TeamSpell = z.looseObject({
  role: z.string(), // HC, OC, DC, OFF_PC, DEF_PC
  name: z.string(),
  start_week: num,
  end_week: nnum.default(null),
  evidence: z.string(),
  confirmed: z.boolean(),
  source_url: nstr.default(null),
})
const TeamChange = TeamSpell.extend({ replaced: nstr.default(null) })
const UnitCaller = z.looseObject({
  name: z.string(),
  confirmed: z.boolean(), // false: this is the coordinator, and nobody is named as the play-caller
  is_head_coach: z.boolean(),
  evidence: nstr.default(null),
  source_url: nstr.default(null),
  situation: nstr.default(null),
  situation_text: nstr.default(null),
  career: z.array(z.looseObject({ team: z.string(), from: num, to: num })).default([]),
  traits: z.array(z.looseObject({ metric: z.string(), label: z.string(), pct: num, seasons: num, first: num, lo: z.string(), hi: z.string() })).default([]),
})
const TeamExpected = z.looseObject({
  pct: num, // 0 to 1, the share of the league below
  miss: nnum.default(null), // typical miss on the same scale; null where no cell was measured
  weight_on_caller: num,
  strength: z.enum(['fair', 'weak']),
})
const TeamSeasonValue = z.looseObject({ pct: num, rate: num, rank: num, of: num })
const TeamMetric = z.looseObject({
  metric: z.string(),
  caller_past: z.looseObject({ pct: num, seasons: num, first: num }).nullable().default(null), // the caller's own seasons before this one
  lean: z.enum(['caller', 'team', 'both']).nullable().default(null), // which past has predicted best, per the study
  label: z.string(),
  help: z.string(),
  unit: z.string(), // pct, seconds, epa
  lo: z.string(), // the axis's ends: less and more, shorter and longer
  hi: z.string(),
  expected: TeamExpected.nullable(),
  caller_seasons: num,
  caller_teams: z.array(z.string()).default([]),
  team_last: TeamSeasonValue.extend({ season: num }).nullable(),
  observed: TeamSeasonValue.extend({ n: num }).nullable(), // charted measures: null until the spring drop
})
const TeamUnit = z.looseObject({
  caller: UnitCaller.nullable(),
  live: z.array(TeamMetric),
  charted: z.array(TeamMetric),
})
export const TeamFile = z.looseObject({
  schema_version: z.string(),
  team: z.string(),
  season: num,
  week: num, // the next week to be played
  through_week: nnum.default(null),
  generated_at: z.string(),
  staff: z.looseObject({ current: z.array(TeamSpell), changes: z.array(TeamChange) }),
  other_starter_weeks: z.array(z.looseObject({ week: num, qb: z.string() })).default([]),
  units: z.looseObject({ off: TeamUnit, def: TeamUnit }),
})
export type TeamFile = z.infer<typeof TeamFile>
export type TeamUnit = z.infer<typeof TeamUnit>
export type TeamMetric = z.infer<typeof TeamMetric>
export type UnitCaller = z.infer<typeof UnitCaller>
export type TeamChange = z.infer<typeof TeamChange>

