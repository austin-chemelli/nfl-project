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
  kind: z.string(), // approach | reference | ensemble | global
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
  last_lock: z.looseObject({ lock_ts: z.string(), season: num, week: num, slot: nstr }).nullable(),
})

// --------------------------------------------------------------------------------------- slate

export const ModelPick = z.looseObject({
  p_home: num,
  spread_home: nnum,
  status: z.enum(['locked', 'backfill', 'preview']),
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

// ------------------------------------------------------------------------------------- tracker

export const Tracker = z.looseObject({
  schema_version: z.string(),
  season: num,
  seasons: z.array(z.looseObject({ season: num, model_id: z.string(), n: num, log_loss: num, brier: num, ece: nnum, spread_mae: nnum })),
  current_season: z.array(z.looseObject({ model_id: z.string(), week: num, n: num, cum_log_loss: num, live: z.boolean() })),
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
    }),
  ),
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
