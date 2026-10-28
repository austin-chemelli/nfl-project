"""Feature group registry (ADR 0012, ADR 0013, docs/feature-groups.md).

A group is a small set of features with a declared direction (sign, for the team) that rolls up into
one composite. Personas and users weigh groups; the weights inside a group are fitted from history
(nfl.approaches.fit). The registry lists planned members too: a member missing from the store is
skipped at fit time, so adding a builder later just makes its features start counting (with a new
REGISTRY_VERSION, since composites change).

Every member and group carries a plain-English label, a one-line description (the UI's hover help),
and a unit that tells the UI how to format values (contract v2: nothing in log-odds reaches a page).

Rules: a feature is in exactly one group; a group is all team-level or all game-level features
(game-level only shift home advantage); `adv` members are hidden behind "more" in the UI. The
market's own forecast (spread, moneyline probability, total) is never a member (ADR 0013).
"""

from __future__ import annotations

from dataclasses import dataclass

# v5 2026-10-28: ml_spread_gap removed from Market behavior (it carried the line's level, review
# finding); live-only scale priors. v4: scheme priors built. v3: Market behavior, labels, units.
REGISTRY_VERSION = "5"

# How the UI formats a value of each unit.
UNITS = {
    "pct": "share 0-1, shown as a percent",
    "pp": "percentage points (already ×100)",
    "prob_diff": "difference of two probabilities 0-1, shown as percentage points",
    "points": "football points",
    "rating": "Elo rating points (1500 = average)",
    "epa": "expected points added per play (or per game where noted)",
    "days": "days",
    "km": "kilometres",
    "hours": "hours",
    "seconds": "seconds",
    "yards": "yards",
    "count": "a count",
    "seasons": "seasons",
    "flag": "yes/no (1/0)",
    "index": "a 0-to-N rating scale described in the feature",
}


@dataclass(frozen=True)
class Member:
    feature: str
    sign: int  # +1 good for the team (home − away > 0 favors home), −1 bad, 0 no prior direction
    label: str
    unit: str
    description: str
    adv: bool = False


@dataclass(frozen=True)
class Group:
    id: str
    name: str
    heading: str  # UI section; carries no weight
    meaning: str
    description: str
    members: tuple[Member, ...]
    game_level: bool = False

    @property
    def features(self) -> list[str]:
        return [m.feature for m in self.members]


def M(
    feature: str, sign: int, label: str, unit: str, description: str, adv: bool = False
) -> Member:
    return Member(feature, sign, label, unit, description, adv)


HEADINGS = [
    "Who's better",
    "Who's playing",
    "The moment",
    "The setup",
    "The sidelines",
    "The outside world",
]

_GROUPS = [
    Group("quality", "Quality", "Who's better", "The better team wins, judged by results",
          "How good each team has been by results: ratings, scoring margin, and schedule.",
          (
              M("strength.elo_pre", 1, "Elo rating", "rating", "A running team-strength rating from game results and margins; 1500 is average."),
              M("strength.point_diff_pg", 1, "Point differential per game", "points", "Points scored minus allowed per game this season, leaning on last season early in the year."),
              M("strength.pythag_win_pct", 1, "Expected win rate (points)", "pct", "The win rate a team's points scored and allowed would normally produce (Pythagorean expectation)."),
              M("strength.sos", 1, "Strength of schedule", "rating", "Average Elo of the opponents faced so far this season."),
              M("strength.luck", -1, "Luck", "prob_diff", "Actual win rate minus expected win rate from points; teams that win more than their points say tend to come back down."),
              M("decisions.turnover_margin_pg", 1, "Turnover margin per game", "count", "Takeaways minus giveaways per game; partly skill, partly luck that regresses."),
              M("strength.st_epa_pg", 1, "Special teams value", "epa", "Expected points added per game by kickoffs, punts, field goals and returns.", adv=True),
          )),
    Group("offense", "Offense", "Who's better", "Efficiency moving the ball",
          "How efficiently each offense moves the ball, per play.",
          (
              M("strength.epa_off", 1, "Offensive EPA per play", "epa", "Expected points added per offensive play: how much each snap improves the scoring outlook. Around 0 is average, +0.1 is very good."),
              M("strength.success_off", 1, "Offensive success rate", "pct", "Share of offensive plays that improve the scoring outlook (EPA above zero)."),
              M("decisions.explosive_rate", 1, "Explosive play rate", "pct", "Share of plays that are passes of 20+ yards or runs of 12+ yards."),
              M("strength.epa_pass_off", 1, "Passing EPA per play", "epa", "Expected points added per pass play, including sacks and scrambles."),
              M("strength.epa_rush_off", 1, "Rushing EPA per play", "epa", "Expected points added per designed run."),
              M("strength.epa_early_off", 1, "Early-down EPA per play", "epa", "EPA per play on first and second down, a steadier signal than third downs.", adv=True),
              M("strength.epa_nongarbage_off", 1, "EPA when the game is in doubt", "epa", "EPA per play excluding garbage time (win probability under 10% or over 90%).", adv=True),
              M("strength.epa_off_adj", 1, "Opponent-adjusted offensive EPA", "epa", "Offensive EPA per play after accounting for the defenses faced.", adv=True),
              M("strength.sack_rate_off", -1, "Sacks allowed rate", "pct", "Share of dropbacks that end in a sack.", adv=True),
              M("front.drop_rate", -1, "Drop rate", "pct", "Share of catchable targets dropped (FTN charting, 2022+).", adv=True),
              M("front.contested_rate", 1, "Contested catch rate", "pct", "Share of targets that are contested catches (FTN charting, 2022+).", adv=True),
          )),
    Group("defense", "Defense", "Who's better", "Efficiency stopping the ball",
          "How efficiently each defense stops the ball, per play (lower allowed is better).",
          (
              M("strength.epa_def", -1, "EPA allowed per play", "epa", "Expected points the defense allows per play; lower is better."),
              M("strength.success_def", -1, "Success rate allowed", "pct", "Share of opponent plays that improve their scoring outlook; lower is better."),
              M("strength.epa_pass_def", -1, "Pass EPA allowed per play", "epa", "Expected points allowed per opponent pass play."),
              M("strength.epa_rush_def", -1, "Rush EPA allowed per play", "epa", "Expected points allowed per opponent designed run."),
              M("strength.sack_rate_def", 1, "Sack rate", "pct", "Share of opponent dropbacks that end in a sack."),
              M("strength.epa_def_adj", -1, "Opponent-adjusted EPA allowed", "epa", "EPA allowed per play after accounting for the offenses faced.", adv=True),
          )),
    Group("quarterback", "Quarterback", "Who's playing", "Who is throwing, and is it the real guy",
          "The projected starting quarterback's track record, and whether he is the usual starter.",
          (
              M("strength.qb_epa", 1, "QB EPA per dropback", "epa", "The projected starter's career expected points added per dropback, recent seasons weighted more; backups sit near replacement level."),
              M("strength.qb_cpoe", 1, "QB completion % over expected", "pp", "How much more often the projected starter completes passes than the difficulty of his throws predicts."),
              M("availability.qb1_out", -1, "Starting QB out", "flag", "The depth-chart starter is listed Out or Doubtful."),
              M("availability.qb_change", -1, "New starter", "flag", "The projected starter is not the quarterback who started the team's last game."),
              M("narrative.qb_status", -1, "QB status (news)", "index", "From the week's reporting: 0 healthy starter, 1 questionable or limited, 2 backup starting or unknown."),
              M("front.int_worthy_rate", -1, "Risky throw rate", "pct", "Share of passes charted as interception-worthy (FTN, 2022+).", adv=True),
          )),
    Group("health", "Health", "Who's playing", "Who is missing",
          "Who is missing from the lineup, weighted by how much the position matters.",
          (
              M("availability.injury_impact", -1, "Injury impact", "index", "Starters listed Out or Doubtful (half for Questionable), weighted by position: QB 5, tackles, edge rushers, top corner and top receiver 2, others 1."),
              M("availability.starters_out", -1, "Starters out", "count", "Depth-chart starters listed Out or Doubtful."),
              M("availability.ol_starters_out", -1, "Offensive line starters out", "count", "Starting centers, guards and tackles listed Out or Doubtful."),
              M("availability.report_count", -1, "Players on the injury report", "count", "Players with an Out, Doubtful or Questionable game status."),
              M("narrative.injury_impact", -1, "Injury impact (news)", "index", "From the week's reporting: 0 nothing notable, 1 a role player or two, 2 a key starter, 3 several key starters or the QB."),
          )),
    Group("form", "Form", "The moment", "Momentum",
          "Recent results and trajectory: is the team hot or cold?",
          (
              M("form.last3_win_pct", 1, "Win rate, last 3 games", "pct", "Wins in the team's last three games (ties count half), across seasons."),
              M("form.last3_margin", 1, "Average margin, last 3 games", "points", "Average point margin over the last three games."),
              M("form.streak", 1, "Streak", "count", "Current winning (+) or losing (−) streak."),
              M("form.epa_trend", 1, "Efficiency trend", "epa", "Net EPA per play over the last four games minus the season average: improving (+) or slipping (−)."),
              M("form.ats_l3", 1, "Beating expectations, last 3", "pct", "Share of the last three games in which the team covered the betting spread."),
          )),
    Group("stakes", "Stakes", "The moment", "What the game means to them",
          "What the game means: trap games, playoff stakes, motivation.",
          (
              M("form.lookahead", -1, "Big game next week", "rating", "How strong next week's opponent is compared with an average team (Elo points)."),
              M("form.letdown", -1, "Coming off a big win", "flag", "Last game was a win over a top-8 team or a primetime division win."),
              M("form.eliminated", -1, "Out of contention", "flag", "Week 13 or later with a win rate under 35%."),
              M("form.clinched", -1, "Coasting", "flag", "Week 13 or later with a win rate over 80%."),
              M("narrative.motivation", 1, "Motivation (news)", "index", "From the week's reporting: −1 nothing to play for, 0 ordinary, +1 must-win."),
              M("narrative.revenge", 1, "Revenge game (news)", "flag", "The week's coverage frames it as a revenge game."),
              M("narrative.lookahead", -1, "Looking ahead (news)", "flag", "The week's coverage frames it as a trap or look-ahead game."),
          )),
    Group("rest_travel", "Rest & travel", "The setup", "Fresh legs and body clocks",
          "Rest days, byes, short weeks, travel distance and time zones.",
          (
              M("environment.rest_days", 1, "Rest days", "days", "Days since the team's last game (capped at 14)."),
              M("form.off_bye", 1, "Off a bye", "flag", "The team's previous game was 13 or more days ago."),
              M("form.short_week", -1, "Short week", "flag", "The team's previous game was 4 or fewer days ago."),
              M("environment.travel_km", -1, "Travel distance", "km", "Distance from the team's home stadium to the venue."),
              M("environment.tz_shift", -1, "Time zones crossed", "hours", "Venue time zone minus home time zone (+ = traveled east)."),
              M("form.road_streak", -1, "Consecutive road games", "count", "Road or neutral games in a row, including this one."),
          )),
    Group("venue_weather", "Venue & weather", "The setup", "Where and in what; shifts home advantage only",
          "Where the game is played and in what conditions; these change how much home field is worth.",
          (
              M("environment.neutral_site", -1, "Neutral site", "flag", "Played at a neutral site (international games, Super Bowl)."),
              M("environment.div_game", -1, "Division game", "flag", "Division rivals, who know each other well."),
              M("environment.primetime", 1, "Primetime", "flag", "Kickoff at 7pm ET or later, or a Thursday or Monday game."),
              M("environment.is_dome", 1, "Dome", "flag", "Played under a closed roof."),
              M("environment.is_turf", 1, "Artificial turf", "flag", "Played on an artificial surface."),
              M("environment.temp_c", -1, "Temperature", "count", "Kickoff temperature in °C (planned)."),
              M("environment.wind_kph", -1, "Wind", "count", "Kickoff wind speed in km/h (planned)."),
              M("narrative.weather_concern", -1, "Weather concern (news)", "index", "From the forecast: 0 dome or mild, 0.5 strong wind or rain, 1 severe."),
          ), game_level=True),
    Group("coaching", "Coaching", "The sidelines", "Decision quality and staff stability",
          "How the staff makes decisions, and how stable the staff is.",
          (
              M("decisions.fourth_go_rate_oe", 1, "4th-down aggressiveness", "prob_diff", "How often the team goes for it on 4th-and-short between the 35s, compared with the league."),
              M("decisions.pass_rate_oe", 1, "Pass rate over expected", "pp", "How much more often the team passes on early downs than the situation predicts."),
              M("decisions.early_down_pass_rate", 1, "Early-down pass rate", "pct", "Share of first- and second-down plays that are passes."),
              M("decisions.hc_tenure", 1, "Head coach tenure", "seasons", "Seasons the current head coach has led the team (planned)."),
              M("decisions.hc_new", -1, "First-year head coach", "flag", "The head coach is in his first season with the team (planned)."),
              M("narrative.coaching_turmoil", -1, "Coaching turmoil (news)", "index", "From the week's reporting: 0 stable, 1 hot seat, firing or public criticism of play-calling."),
              M("decisions.proe_leading", 1, "Pass rate over expected when ahead", "pp", "Pass rate over expected when leading by 7 or more (planned).", adv=True),
              M("decisions.proe_trailing", 1, "Pass rate over expected when behind", "pp", "Pass rate over expected when trailing by 7 or more (planned).", adv=True),
              M("decisions.pace", 1, "Pace", "seconds", "Seconds per offensive play in neutral situations (planned).", adv=True),
              M("decisions.penalty_yds_pg", -1, "Penalty yards per game", "yards", "Penalty yards against per game (planned).", adv=True),
              M("decisions.hc_ats_career", 1, "Head coach vs the spread", "pct", "The head coach's career rate of covering the betting spread (planned).", adv=True),
          )),
    Group("off_scheme", "Offensive scheme", "The sidelines", "How the offense is built (style; history decides what helps)",
          "How the offense is built: motion, play-action, formations, personnel. Style, not quality; history decides what helps.",
          (
              M("front.motion_rate", 1, "Pre-snap motion", "pct", "Share of plays with a player in motion before the snap (FTN, 2022+)."),
              M("front.play_action_rate", 1, "Play-action", "pct", "Share of passes with a play-action fake (FTN, 2022+)."),
              M("front.rpo_rate", 1, "Run-pass options", "pct", "Share of plays that are RPOs (FTN, 2022+; planned)."),
              M("front.screen_rate", -1, "Screens", "pct", "Share of passes that are screens (FTN, 2022+; planned)."),
              M("front.under_center_rate", -1, "Under center", "pct", "Share of plays with the QB under center (FTN, 2022+; planned)."),
              M("front.no_huddle_rate", 1, "No-huddle", "pct", "Share of plays run without a huddle (FTN, 2022+; planned)."),
              M("scheme.off_11_rate_prior", 1, "Three-receiver sets (coordinator history)", "pct", "How often the offensive play-caller has used 11 personnel in past seasons, relative to each season's league average (participation 2016+; coverage 2018+)."),
              M("scheme.off_heavy_rate_prior", -1, "Heavy sets (coordinator history)", "pct", "How often the play-caller has used two-plus tight ends or backs in past seasons, relative to each season's league average (participation 2016+; coverage 2018+)."),
              M("scheme.off_time_to_throw_prior", -1, "Time to throw (coordinator history)", "seconds", "Average time to throw in the play-caller's past offenses, relative to each season's league average (participation 2016+)."),
          )),
    Group("def_scheme", "Defensive scheme", "The sidelines", "How the defense is built",
          "How the defense is built: blitzes, boxes, coverage habits. Style, not quality.",
          (
              M("front.blitz_rate", 1, "Blitz rate", "pct", "Share of opponent dropbacks with at least one blitzer (FTN, 2022+)."),
              M("front.box_8plus_rate", 1, "Stacked boxes vs the run", "pct", "Share of opponent runs faced with 8+ defenders in the box (FTN, 2022+)."),
              M("front.pass_rushers_5plus_rate", 1, "Five-plus rushers", "pct", "Share of dropbacks with five or more pass rushers (FTN, 2022+; planned)."),
              M("scheme.def_man_rate_prior", 1, "Man coverage (coordinator history)", "pct", "How often the defensive play-caller has played man coverage in past seasons, relative to each season's league average (participation 2016+; coverage 2018+)."),
              M("scheme.def_two_high_rate_prior", -1, "Two-high shells (coordinator history)", "pct", "How often the play-caller has played two-deep safety shells in past seasons, relative to each season's league average (participation 2016+; coverage 2018+)."),
              M("scheme.def_pressure_rate_prior", 1, "Pressure rate (coordinator history)", "pct", "Pressure rate in the play-caller's past defenses, relative to each season's league average (participation 2016+)."),
          )),
    Group("matchups", "Matchups", "The sidelines", "This offense against this defense",
          "This offense's habits against this defense's habits (planned).",
          (
              M("matchup.pa_vs_pa_defense", 1, "Play-action vs a defense that struggles with it", "index", "Offense's play-action habit times the defense's results against play-action (planned)."),
              M("matchup.blitz_vs_blitz_offense", 1, "Blitz vs an offense that struggles with it", "index", "Defense's blitz habit times the offense's results against the blitz (planned)."),
              M("matchup.motion_vs_motion_defense", 1, "Motion vs a defense that struggles with it", "index", "Offense's motion habit times the defense's results against motion (planned)."),
              M("matchup.under_center_vs_light_box", 1, "Power runs vs light boxes", "index", "Under-center run game against a defense that plays light boxes (planned)."),
              M("matchup.off_vs_man", 1, "Offense vs man coverage", "index", "Offense's results against man coverage times the defense's man rate (planned)."),
              M("matchup.off_vs_pressure", 1, "Offense vs pressure", "index", "Offense's results under pressure times the defense's pressure rate (planned)."),
              M("matchup.off_11_vs_def_11", 1, "Three-receiver sets vs the defense", "index", "Offense's 11-personnel results against the defense's results versus 11 personnel (planned)."),
          )),
    Group("market", "Market behavior", "The outside world", "How the betting market is behaving (not what it predicts)",
          "How the betting market is behaving: line movement and where the public is. Never the line itself (ADR 0013); live only, so it contributes nothing to backtests.",
          (
              M("market.line_move_pts", 1, "Line movement", "points", "How far the spread has moved toward the home team since the week's first snapshot (live only)."),
              M("narrative.public_bet_pct_home", 0, "Public betting on the home team", "pct", "Share of spread bets on the home team from consensus pages (live only)."),
          ), game_level=True),
    Group("buzz", "Buzz", "The outside world", "Media and public mood (live only)",
          "The mood of the week's coverage (live only).",
          (
              M("narrative.sentiment", 1, "Media sentiment", "index", "Tone of the week's coverage of the team, from −1 (negative) to +1 (positive)."),
              M("narrative.hype", 1, "Hype", "index", "How much national coverage the team is getting this week, 0 to 1."),
          )),
]  # fmt: skip

GROUPS: dict[str, Group] = {g.id: g for g in _GROUPS}
FEATURE_GROUP: dict[str, str] = {m.feature: g.id for g in _GROUPS for m in g.members}
MEMBERS: dict[str, Member] = {m.feature: m for g in _GROUPS for m in g.members}
# The market's own forecast: never an approach input (ADR 0013).
# The moneyline-vs-spread gap is in here too: p_ml − Φ(spread/13.5) is mostly a monotone function of
# the spread (corr 0.63, review 2026-10-28), so it carried the line's level.
MARKET_LEVEL = {
    "market.spread_line",
    "market.p_home_vigfree",
    "market.total_line",
    "market.key_number",
    "market.ml_spread_gap",
}

# Scale priors (mean, sd) for live-only members, used by the Scaler when a feature has too little
# history to standardize (review 2026-10-28: unscaled live inputs swung the Sharp by up to 0.8 logit).
LIVE_PRIORS: dict[str, tuple[float, float]] = {
    "market.line_move_pts": (0.0, 1.5),
    "narrative.public_bet_pct_home": (0.5, 0.15),
    "narrative.qb_status": (0.3, 0.6),
    "narrative.injury_impact": (1.0, 1.0),
    "narrative.sentiment": (0.0, 0.4),
    "narrative.hype": (0.4, 0.25),
    "narrative.coaching_turmoil": (0.1, 0.2),
    "narrative.motivation": (0.0, 0.4),
    "narrative.revenge": (0.05, 0.2),
    "narrative.lookahead": (0.05, 0.2),
    "narrative.weather_concern": (0.15, 0.25),
}
MARKET_GROUP_CAP = 0.20  # max share of a persona's attention budget on Market behavior


def validate_registry() -> None:
    seen: dict[str, str] = {}
    for g in _GROUPS:
        if g.heading not in HEADINGS:
            raise ValueError(f"{g.id}: unknown heading {g.heading!r}")
        for m in g.members:
            if m.feature in seen:
                raise ValueError(f"{m.feature} in both {seen[m.feature]} and {g.id}")
            if m.feature in MARKET_LEVEL:
                raise ValueError(f"{m.feature} is the market's forecast; never a group member")
            if m.unit not in UNITS:
                raise ValueError(f"{m.feature}: unknown unit {m.unit!r}")
            if not m.description or not m.label:
                raise ValueError(f"{m.feature}: label and description required")
            seen[m.feature] = g.id


validate_registry()
