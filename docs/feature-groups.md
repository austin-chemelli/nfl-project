# Feature groups

The two-level feature design is ADR 0012. This file is the group registry in prose; the code registry is `src/nfl/features/groups.py` (M2.8). Chosen 2026-10-27 (option B of `.notes/feature-group-options.md`, with the scheme group split three ways). Signs are the declared default direction *for the team* (positive = good for the home team when home − away is positive); the fitted inner weights may disagree, and the Hypotheses page reports when they do. "Exists" means built as of 2026-10-27; everything else has a task in `docs/tasks.md`. Members marked *adv* are hidden behind "more" in the UI but always part of the composite once built.

Fifteen groups. The UI may show them under six collapsible headings (Who's better / Who's playing / The moment / The setup / The sidelines / The outside world); the headings carry no weights.

| Group | Members (sign) | Exists | What the slider means |
|---|---|---|---|
| **Quality** | `strength.elo_pre` (+), `strength.point_diff_pg` (+), `strength.pythag_win_pct` (+), `strength.sos` (+), `strength.luck` (−), `decisions.turnover_margin_pg` (+), *adv* `strength.st_epa_pg` (+) | first two | "The better team wins", results-based |
| **Offense** | `strength.epa_off` (+), `strength.success_off` (+), `decisions.explosive_rate` (+), `strength.epa_pass_off` (+), `strength.epa_rush_off` (+), *adv* `strength.epa_early_off` (+), `strength.epa_nongarbage_off` (+), `strength.epa_off_adj` (+), `strength.sack_rate_off` (−), `front.drop_rate` (−), `front.contested_rate` (+) | first three | Efficiency moving the ball |
| **Defense** | `strength.epa_def` (−), `strength.success_def` (−), `strength.epa_pass_def` (−), `strength.epa_rush_def` (−), `strength.sack_rate_def` (+), *adv* `strength.epa_def_adj` (−) | first two | Efficiency stopping the ball |
| **Quarterback** | `strength.qb_epa` (+), `strength.qb_cpoe` (+), `availability.qb1_out` (−), `availability.qb_change` (−), `narrative.qb_status` (−), *adv* `front.int_worthy_rate` (−) | none | Who is throwing, and is it the real guy |
| **Health** | `availability.injury_impact` (−), `availability.starters_out` (−), `availability.ol_starters_out` (−), `availability.report_count` (−), `narrative.injury_impact` (−) | none | Who is missing |
| **Form** | `form.last3_win_pct` (+), `form.last3_margin` (+), `form.streak` (+), `form.epa_trend` (+), `form.ats_l3` (+) | first three | Momentum |
| **Stakes** | `form.lookahead` (−), `form.letdown` (−), `form.eliminated` (−), `form.clinched` (−), `narrative.motivation` (+), `narrative.revenge` (+), `narrative.lookahead` (−) | none | What the game means to them |
| **Rest & travel** | `environment.rest_days` (+), `form.off_bye` (+), `form.short_week` (−), `environment.travel_km` (−), `environment.tz_shift` (−), `form.road_streak` (−) | rest, travel, tz | Fresh legs and body clocks |
| **Venue & weather** | game-level: `environment.neutral_site` (−), `environment.div_game` (−), `environment.primetime` (+), `environment.is_dome` (+), `environment.is_turf` (+), `environment.temp_c` (−), `environment.wind_kph` (−), `narrative.weather_concern` (−) | first five | Where and in what; shifts home advantage only |
| **Coaching** | `decisions.fourth_go_rate_oe` (+), `decisions.pass_rate_oe` (+), `decisions.early_down_pass_rate` (+), `decisions.hc_tenure` (+), `decisions.hc_new` (−), `narrative.coaching_turmoil` (−), *adv* `decisions.proe_leading` (+), `decisions.proe_trailing` (+), `decisions.pace` (+), `decisions.penalty_yds_pg` (−), `decisions.hc_ats_career` (+) | first four | Decision quality and staff stability |
| **Offensive scheme** | `front.motion_rate` (+), `front.play_action_rate` (+), `front.rpo_rate` (+), `front.screen_rate` (−), `front.under_center_rate` (−), `front.no_huddle_rate` (+), `scheme.off_11_rate_prior` (+), `scheme.off_heavy_rate_prior` (−), `scheme.off_time_to_throw_prior` (−) | motion, PA | How the offense is built (style; the fit decides what helps) |
| **Defensive scheme** | `front.blitz_rate` (+), `front.box_8plus_rate` (+), `front.pass_rushers_5plus_rate` (+), `scheme.def_man_rate_prior` (+), `scheme.def_two_high_rate_prior` (−), `scheme.def_pressure_rate_prior` (+) | blitz, box | How the defense is built |
| **Matchups** | `matchup.pa_vs_pa_defense`, `matchup.blitz_vs_blitz_offense`, `matchup.motion_vs_motion_defense`, `matchup.under_center_vs_light_box`, `matchup.off_vs_man`, `matchup.off_vs_pressure`, `matchup.off_11_vs_def_11` (all +: offense's edge in that interaction) | none | This offense against this defense specifically |
| **Market** | `market.spread_line` (+), `market.line_move_pts` (+), `market.ml_spread_gap` (+), `narrative.public_bet_pct_home` (+), *adv* `market.total_line` (no prior direction), `market.key_number` (no prior direction) | spread, total, move | What the line says |
| **Buzz** | `narrative.sentiment` (+), `narrative.hype` (+) | contract only | Media and public mood. Live only; "weeks tracked" applies |

Not in any group: `market.p_home_vigfree` (a restatement of the line, used for divergence and the ledger), `narrative.upset_buzz` (game-level, while Buzz is team-level; shown on the game page), `narrative.public_pick` (categorical). The code registry is the source of truth when this table and `src/nfl/features/groups.py` disagree.

Rules:
- A feature is in exactly one group. Turnover margin is under Quality (moved from Coaching 2026-10-27: it's a results stat that partly regresses, like `luck`, not a coaching decision). Interception-worthy throws are a QB trait, drops and contested catches are receiver traits, so they live in Quarterback and Offense, not scheme.
- Style features (scheme groups) have no inherent "good" direction; the declared sign is a prior and the fitted inner weight decides. A persona weighting Offensive scheme positively means "I trust modern scheme traits, as the data weighs them".
- Narrative members are null (league average) for every historical game, so they contribute nothing to backtests and only matter live. Composites still have unit variance on the training window because the null-as-zero convention holds there too.
- Game-level members enter as standardized values, not differences; they can only move home advantage.
- Scheme and Matchups groups are 2022+ (FTN) and 2016+ (participation priors); the UI labels coverage on those sliders.
- Adding a member to a group changes the composite, so the group registry carries a version that is written into every fit artifact.

Persona group weights (to be re-proposed in M2.8, for Austin's review): the Traditionalist leans Quality, Form, Rest & travel, Venue & weather; the Analyst leans Offense, Defense, Coaching, Quarterback; the Sharp leans Market with small contrarian Form and Buzz; the Narrative (shadow) leans Buzz, Health, Quarterback, Stakes; the Matchup (offseason) leans Matchups, Offensive scheme, Defensive scheme.
