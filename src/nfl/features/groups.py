"""Feature group registry (ADR 0012, docs/feature-groups.md).

A group is a small set of features with a declared direction (sign, for the team) that rolls up into
one composite. Personas and users weigh groups; the weights inside a group are fitted from history
(nfl.approaches.fit). The registry lists planned members too: a member missing from the store is
skipped at fit time, so adding a builder later just makes its features start counting (with a new
REGISTRY_VERSION, since composites change).

Rules: a feature is in exactly one group; a group is all team-level or all game-level features
(game-level only shift home advantage); `adv` members are hidden behind "more" in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass

REGISTRY_VERSION = "2"  # v2 2026-10-27: turnover margin moved from Coaching to Quality


@dataclass(frozen=True)
class Member:
    feature: str
    sign: int  # +1 good for the team (home − away > 0 favors home), −1 bad, 0 no prior direction
    adv: bool = False


@dataclass(frozen=True)
class Group:
    id: str
    name: str
    heading: str  # UI section; carries no weight
    meaning: str
    members: tuple[Member, ...]
    game_level: bool = False

    @property
    def features(self) -> list[str]:
        return [m.feature for m in self.members]


def _m(spec: str) -> tuple[Member, ...]:
    """'+strength.elo_pre -strength.luck ~market.total_line *+x.y' : sign prefix, '*' = adv."""
    out = []
    for tok in spec.split():
        adv = tok.startswith("*")
        tok = tok.lstrip("*")
        sign = {"+": 1, "-": -1, "~": 0}[tok[0]]
        out.append(Member(tok[1:], sign, adv))
    return tuple(out)


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
          _m("+strength.elo_pre +strength.point_diff_pg +strength.pythag_win_pct +strength.sos "
             "-strength.luck +decisions.turnover_margin_pg *+strength.st_epa_pg")),
    Group("offense", "Offense", "Who's better", "Efficiency moving the ball",
          _m("+strength.epa_off +strength.success_off +decisions.explosive_rate "
             "+strength.epa_pass_off +strength.epa_rush_off *+strength.epa_early_off "
             "*+strength.epa_nongarbage_off *+strength.epa_off_adj *-strength.sack_rate_off "
             "*-front.drop_rate *+front.contested_rate")),
    Group("defense", "Defense", "Who's better", "Efficiency stopping the ball",
          _m("-strength.epa_def -strength.success_def -strength.epa_pass_def "
             "-strength.epa_rush_def +strength.sack_rate_def *-strength.epa_def_adj")),
    Group("quarterback", "Quarterback", "Who's playing", "Who is throwing, and is it the real guy",
          _m("+strength.qb_epa +strength.qb_cpoe -availability.qb1_out -availability.qb_change "
             "-narrative.qb_status *-front.int_worthy_rate")),
    Group("health", "Health", "Who's playing", "Who is missing",
          _m("-availability.injury_impact -availability.starters_out "
             "-availability.ol_starters_out -availability.report_count -narrative.injury_impact")),
    Group("form", "Form", "The moment", "Momentum",
          _m("+form.last3_win_pct +form.last3_margin +form.streak +form.epa_trend +form.ats_l3")),
    Group("stakes", "Stakes", "The moment", "What the game means to them",
          _m("-form.lookahead -form.letdown -form.eliminated -form.clinched "
             "+narrative.motivation +narrative.revenge -narrative.lookahead")),
    Group("rest_travel", "Rest & travel", "The setup", "Fresh legs and body clocks",
          _m("+environment.rest_days +form.off_bye -form.short_week -environment.travel_km "
             "-environment.tz_shift -form.road_streak")),
    Group("venue_weather", "Venue & weather", "The setup",
          "Where and in what; shifts home advantage only",
          _m("-environment.neutral_site -environment.div_game +environment.primetime "
             "+environment.is_dome +environment.is_turf -environment.temp_c "
             "-environment.wind_kph -narrative.weather_concern"),
          game_level=True),
    Group("coaching", "Coaching", "The sidelines", "Decision quality and staff stability",
          _m("+decisions.fourth_go_rate_oe +decisions.pass_rate_oe "
             "+decisions.early_down_pass_rate "
             "+decisions.hc_tenure -decisions.hc_new -narrative.coaching_turmoil "
             "*+decisions.proe_leading *+decisions.proe_trailing *+decisions.pace "
             "*-decisions.penalty_yds_pg *+decisions.hc_ats_career")),
    Group("off_scheme", "Offensive scheme", "The sidelines",
          "How the offense is built (style; history decides what helps)",
          _m("+front.motion_rate +front.play_action_rate +front.rpo_rate -front.screen_rate "
             "-front.under_center_rate +front.no_huddle_rate +scheme.off_11_rate_prior "
             "-scheme.off_heavy_rate_prior -scheme.off_time_to_throw_prior")),
    Group("def_scheme", "Defensive scheme", "The sidelines", "How the defense is built",
          _m("+front.blitz_rate +front.box_8plus_rate +front.pass_rushers_5plus_rate "
             "+scheme.def_man_rate_prior -scheme.def_two_high_rate_prior "
             "+scheme.def_pressure_rate_prior")),
    Group("matchups", "Matchups", "The sidelines", "This offense against this defense",
          _m("+matchup.pa_vs_pa_defense +matchup.blitz_vs_blitz_offense "
             "+matchup.motion_vs_motion_defense +matchup.under_center_vs_light_box "
             "+matchup.off_vs_man +matchup.off_vs_pressure +matchup.off_11_vs_def_11")),
    Group("market", "Market", "The outside world", "What the line says",
          _m("+market.spread_line +market.line_move_pts +market.ml_spread_gap "
             "+narrative.public_bet_pct_home *~market.total_line *~market.key_number"),
          game_level=True),
    Group("buzz", "Buzz", "The outside world", "Media and public mood (live only)",
          _m("+narrative.sentiment +narrative.hype")),
]  # fmt: skip

GROUPS: dict[str, Group] = {g.id: g for g in _GROUPS}
FEATURE_GROUP: dict[str, str] = {m.feature: g.id for g in _GROUPS for m in g.members}


def validate_registry() -> None:
    seen: dict[str, str] = {}
    for g in _GROUPS:
        if g.heading not in HEADINGS:
            raise ValueError(f"{g.id}: unknown heading {g.heading!r}")
        for m in g.members:
            if m.feature in seen:
                raise ValueError(f"{m.feature} in both {seen[m.feature]} and {g.id}")
            seen[m.feature] = g.id


validate_registry()
