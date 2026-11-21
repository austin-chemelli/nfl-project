# Feature groups

Status: current, verified 2026-11-20 (registry v7, model wave 3, ADR 0031).

The two-level feature design is ADR 0012. This file is the group registry in prose; the code registry is `src/nfl/features/groups.py` (M2.8). Chosen 2026-10-27 (option B of `.notes/feature-group-options.md`, with the scheme group split three ways). Signs are the declared default direction *for the team* (positive = good for the home team when home − away is positive); the fitted inner weights may disagree, and the Hypotheses page reports when they do. "Exists" means built as of 2026-10-27; everything else has a task in `docs/tasks.md`. Members marked *adv* are hidden behind "more" in the UI but always part of the composite once built.

Sixteen groups, 94 members, every one built (registry v7, ADR 0031: nothing is "planned" any more; a member is in the store or out of the registry on purpose). `coaching`, `off_scheme`, `def_scheme` and `matchups` are context-only (ADR 0018): shown, never weighted. The Student weighs every football group except Venue & weather (its fitted modifiers cost accuracy since 2016); the Traditionalist still weighs it. **Home field is zero at a neutral site by rule** for every approach (engine.NEUTRAL), so `environment.neutral_site` is not a member. The UI may show the groups under six collapsible headings (Who's better / Who's playing / The moment / The setup / The sidelines / The outside world); the headings carry no weights. "In the line" on a page means a member of a weighted group.

| Group | Members (sign) | What the slider means |
|---|---|---|
| **Quality** | `strength.elo_pre` (+), `strength.point_diff_pg` (+), `strength.pythag_win_pct` (+), `strength.sos` (+), `strength.luck` (−), `decisions.turnover_margin_pg` (+) | "The better team wins", results-based |
| **Offense** | `strength.epa_off` (+), `strength.success_off` (+), `decisions.explosive_rate` (+), **`matchup.net_edge_pg` (+, wave 3)**, `strength.epa_pass_off` (+), `strength.epa_rush_off` (+), *adv* `strength.epa_early_off` (+), `strength.epa_nongarbage_off` (+), `strength.epa_off_adj` (+), `strength.sack_rate_off` (−) | Efficiency moving the ball, and how this offense's habits meet this defense |
| **Defense** | `strength.epa_def` (−), `strength.success_def` (−), `strength.epa_pass_def` (−), `strength.epa_rush_def` (−), `strength.sack_rate_def` (+), *adv* `strength.epa_def_adj` (−), `scheme.def_pressure_rate_prior` (+) | Efficiency stopping the ball |
| **Special teams** | `strength.st_epa_pg` (+), `strength.st_kicking_epa_pg` (+), `strength.st_punt_epa_pg` (+), `strength.st_kickoff_epa_pg` (+) | Kicking and field position |
| **Quarterback** | `strength.qb_epa` (+), `strength.qb_cpoe` (+), `availability.qb1_out` (−), `availability.qb_change` (−), `narrative.qb_status` (−) | Who is throwing, and is it the real guy |
| **Health** | `availability.injury_impact` (−), `availability.starters_out` (−), `availability.ol_starters_out` (−), `availability.report_count` (−), `narrative.injury_impact` (−) | Who is missing |
| **Form** | `form.last3_win_pct` (+), `form.last3_margin` (+), `form.streak` (+), `form.epa_trend` (+), `form.ats_l3` (+) | Momentum |
| **Stakes** | `form.lookahead` (−), `form.letdown` (−), `form.eliminated` (−), `form.clinched` (−), `narrative.motivation` (+), `narrative.revenge` (+), `narrative.lookahead` (−) | What the game means to them |
| **Rest & travel** | `environment.rest_days` (+), `form.off_bye` (+), `form.short_week` (−), `environment.travel_km` (−), `environment.tz_shift` (−), `form.road_streak` (−) | Fresh legs and body clocks |
| **Venue & weather** (game-level) | `environment.div_game` (−), `environment.primetime` (+), `environment.is_dome` (+), `environment.is_turf` (+), `narrative.weather_concern` (−) | Where and in what; shifts home advantage only, and is zero at a neutral site. The Traditionalist's group, not the Student's |
| **Coaching** (context) | `decisions.fourth_go_rate_oe`, `pass_rate_oe`, `early_down_pass_rate`, `hc_tenure`, `hc_new`, `narrative.coaching_turmoil`, *adv* `proe_leading`, `proe_trailing`, `pace`, `penalty_yds_pg` | Decision quality and staff stability |
| **Offensive scheme** (context) | `front.motion_rate`, `play_action_rate`, `rpo_rate`, `screen_rate`, `under_center_rate`, `no_huddle_rate`, `scheme.off_11_rate_prior`, `off_heavy_rate_prior`, `off_time_to_throw_prior` | How the offense is built |
| **Defensive scheme** (context) | `front.blitz_rate`, `box_8plus_rate`, `scheme.def_man_rate_prior`, `def_two_high_rate_prior` | How the defense is built |
| **Matchups** (context) | `matchup.edge_blitz`, `edge_box_light`, `edge_box_heavy`, `edge_play_action`, `edge_motion`, `edge_screen`, `edge_rpo` (all *adv*) | Each situation's edge on its own: shown, not scored (only their sum, in Offense, passed the gates) |
| **Market behavior** (ADR 0013) | `market.line_move_pts` (+), `narrative.public_bet_pct_home` (no prior direction) | How the betting market is *behaving*, never what it predicts; capped at 20% of a persona's budget; live only |
| **Buzz** | `narrative.sentiment` (+), `narrative.hype` (+) | Media and public mood. Live only |

Built but in no group, with their ledger rows (`nfl candidates list`): `front.drop_rate`, `front.contested_rate`, `front.int_worthy_rate` (together +0.0013 log loss since 2022: switched on, they made the Student worse), `strength.epa_off_noto`, `epa_def_noto`, `takeaway_rate`, `fum_luck`, `decisions.one_score_luck`, `availability.value_lost`, `availability.ol_weakest` (none beat the Student in shadow). Removed from the registry: `decisions.hc_ats_career` (a spread record: the market's number), `front.pass_rushers_5plus_rate` (identical to the blitz rate), the seven planned `matchup.*` interactions (replaced by the engine's edges), `environment.neutral_site` (now a rule), and the planned `environment.temp_c` / `wind_kph` (the store's `weather.*` stays out of every fit: observed in training, forecast at a lock; it waits for archived forecasts, M23.14).

Not in any group, by ADR 0013 (the market's forecast is the reference, never an input): `market.spread_line`, `market.p_home_vigfree`, `market.total_line`. Also not in a group: `narrative.upset_buzz` (game-level, shown on the game page), `narrative.public_pick` (categorical). The code registry is the source of truth when this table and `src/nfl/features/groups.py` disagree.

Rules:
- A feature is in exactly one group. Turnover margin is under Quality (moved from Coaching 2026-10-27: it's a results stat that partly regresses, like `luck`, not a coaching decision). Interception-worthy throws are a QB trait, drops and contested catches are receiver traits, so they live in Quarterback and Offense, not scheme.
- Style features (scheme groups) have no inherent "good" direction; the declared sign is a prior and the fitted inner weight decides. A persona weighting Offensive scheme positively means "I trust modern scheme traits, as the data weighs them".
- Narrative members are null (league average) for every historical game, so they contribute nothing to backtests and only matter live. Composites still have unit variance on the training window because the null-as-zero convention holds there too.
- Game-level members enter as standardized values, not differences; they can only move home advantage.
- Scheme and Matchups groups are 2022+ (FTN) and 2016+ (participation priors); the UI labels coverage on those sliders.
- Adding a member to a group changes the composite, so the group registry carries a version that is written into every fit artifact.
- A member joins a weighted group only with a ledger row whose shadow gate passed (verdict `model`, ADR 0031); a member whose group is context-only is shown, not scored.

Persona group weights live in `src/nfl/approaches/configs/*.yaml`, each with its `why`; wave 3's changes are in ADR 0031.
