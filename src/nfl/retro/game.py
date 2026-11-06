"""Game retrospective builder (M9.4, ADR 0016, architecture §3.6c).

`build_games` writes `marts/retro/season=S/<game_id>.json` (shape: `nfl.retro.schema.RetroGame`)
for finished games of a season. Everything is computed from curated plays, the expectations file
and the prediction rows the game page shows; every sentence is a template over the same numbers.

Judgment calls (also in the docs of each helper):
- Season-to-date and league figures use the plays of the season's games that kicked off strictly
  before this game (any season_type), so a later game never changes an earlier game's record.
- The interception expectation shrinks the team's season-to-date rate per dropback toward the
  league's with 150 pseudo-dropbacks. The league rate is the league's season to date once it has
  300 dropbacks, else the previous season's rate (else a 2.3% constant): early in a season the
  league-to-date is a handful of plays.
- With no earlier game the penalty expectation is the league's per team-game (else 55 yards).
- 3rd/4th-down attempts exclude interceptions, lost fumbles and aborted plays, and the kicking
  factor excludes blocked FGs (v2 expectations): those are priced by the turnover and
  special-teams factors, never twice.
- A retro is rebuilt only when its game's plays (a hash of the columns read here) or the
  expectations version change, or with `--force`; a new nflverse snapshot with identical plays
  rewrites nothing. `pbp_snapshot_ts` is information. A game with no lock or backfill always
  gets its approaches scored as of kickoff - 1h (`site.pregame_rows(game_ids=...)`), whatever
  the week window.
- Probabilities are stored to 4 decimals, EPA and rates to 3, swings and pp to 1.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import polars as pl

from nfl.config import Paths, current_season, now_utc
from nfl.retro.expectations import _in_bucket, expectations_path, load
from nfl.retro.schema import (
    SCHEMA_VERSION,
    Attribution,
    Bucket,
    Drive,
    Efficiency,
    Expectations,
    GradedPick,
    GroupValue,
    LuckFactor,
    Phase,
    PlayedLike,
    Result,
    RetroGame,
    TeamRetro,
    WpPlay,
    WpSeries,
)

INT_PRIOR_DROPBACKS = 150
LEAGUE_INT_MIN_DROPBACKS = 300
DEFAULT_INT_RATE = 0.023
DEFAULT_PENALTY_YARDS = 55.0
CLIP = (0.001, 0.999)
APPROACH_KINDS = ("approach", "ensemble")

PLAY_COLS = [
    "game_id", "play_id", "raw_snapshot_ts", "aborted_play", "posteam", "defteam", "play_type", "epa", "success",
    "qb_dropback", "sack", "yards_gained", "pass_oe", "interception", "fumble", "fumble_lost",
    "special_teams_play", "down", "ydstogo", "third_down_converted", "third_down_failed",
    "fourth_down_converted", "fourth_down_failed", "field_goal_attempt", "field_goal_result",
    "kick_distance", "extra_point_attempt", "extra_point_result", "penalty_team", "penalty_yards",
    "return_touchdown", "td_team", "punt_blocked", "drive", "yardline_100", "touchdown",
    "qtr", "game_seconds_remaining", "desc", "season_type", "vegas_home_wp", "vegas_home_wpa",
    "fixed_drive", "fixed_drive_result", "drive_start_yard_line", "drive_end_yard_line",
    "drive_play_count",
]  # fmt: skip
TEXT_COLS = {  # the rest are doubles; only matters for a column a partition lacks
    "game_id", "raw_snapshot_ts", "posteam", "defteam", "play_type", "field_goal_result",
    "extra_point_result", "penalty_team", "td_team", "desc", "season_type", "fixed_drive_result",
    "drive_start_yard_line", "drive_end_yard_line",
}  # fmt: skip

OFF_LABELS = {
    "epa_play": ("EPA per play", "epa"),
    "success": ("Success rate", "pct"),
    "epa_dropback": ("EPA per dropback", "epa"),
    "epa_rush": ("EPA per rush", "epa"),
    "explosive": ("Explosive-play rate", "pct"),
    "sack_rate": ("Sack rate", "pct"),
    "proe": ("Pass rate over expected", "pp"),
}
DEF_LABELS = {
    "epa_play": "EPA per play allowed",
    "success": "Success rate allowed",
    "epa_dropback": "EPA per dropback allowed",
    "epa_rush": "EPA per rush allowed",
    "explosive": "Explosive plays allowed",
    "sack_rate": "Sack rate (defense)",
    "proe": "Opponent pass rate over expected",
}


# ----------------------------------------------------------------------------------------- helpers


def _canon(col: str) -> pl.Expr:
    from nfl.models.elo import TEAM_ALIASES

    return pl.col(col).replace(TEAM_ALIASES)


def _alias(team: str) -> str:
    from nfl.models.elo import TEAM_ALIASES

    return TEAM_ALIASES.get(team, team)


def _names() -> dict[str, str]:
    from nfl.odds import TEAMS

    return {abbr: name for name, abbr in TEAMS.items()}


def _z(x: float, nd: int) -> float:
    """round() that never returns -0.0 (so JSON and `{:+.1f}` never print a negative zero)."""
    return round(float(x), nd) + 0.0


def _plural(n: float, one: str, many: str | None = None) -> str:
    return one if int(n) == 1 else (many or one + "s")


def _sig(x: float) -> str:
    return f"{x:+.1f}"


def _ll(p: float, y: float) -> float:
    """Cross-entropy of the home win probability p against y (1 home win, 0 away, 0.5 tie)."""
    p = min(max(p, CLIP[0]), CLIP[1])
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def _expit(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _ts(x: datetime) -> str:
    return x.strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------------------------------- data


def _load_plays(paths: Paths, season: int) -> pl.DataFrame:
    """The season's plays. Reads `season={S}/*.parquet` only: a glob across seasons binds to the
    first file's schema, so a column older partitions lack would be a Binder Error (daily.py).
    A partition that predates some columns gets them as typed nulls; no partition, an empty frame."""
    files = f"{paths.curated_table('plays').as_posix()}/season={int(season)}/*.parquet"
    if not list(Path(files).parent.glob("*.parquet")):
        df = pl.DataFrame(schema={c: pl.Utf8 if c in TEXT_COLS else pl.Float64 for c in PLAY_COLS})
    else:
        src = f"read_parquet('{files}', hive_partitioning=false, union_by_name=true)"
        have = set(duckdb.sql(f"select * from {src} limit 0").columns)
        sel = ", ".join(
            f'"{c}"'
            if c in have
            else f'cast(null as {"varchar" if c in TEXT_COLS else "double"}) as "{c}"'
            for c in PLAY_COLS
        )
        df = duckdb.sql(f"select {sel} from {src}").pl()
    return df.with_columns(
        _canon("posteam"), _canon("defteam"), _canon("penalty_team"), _canon("td_team")
    )


def _load_games(paths: Paths, season: int) -> pl.DataFrame:
    from nfl.features import store

    return (
        store.games_frame(paths)
        .filter(pl.col("season") == season)
        .with_columns(pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us")))
    )


def _prior_league_int_rate(paths: Paths, season: int) -> float:
    """League interceptions per dropback in the previous season (the week-1 fallback)."""
    glob = f"{paths.curated_table('plays').as_posix()}/*/*.parquet"
    try:
        r = duckdb.sql(
            f"select sum(case when interception = 1 then 1 else 0 end), count(*) "
            f"from read_parquet('{glob}', hive_partitioning=true) "
            f"where season = {int(season) - 1} and season_type = 'REG' and qb_dropback = 1 "
            f"and play_type in ('pass','run') and epa is not null"
        ).fetchall()
    except duckdb.Error:
        return DEFAULT_INT_RATE
    return r[0][0] / r[0][1] if r and r[0][1] else DEFAULT_INT_RATE


def league_int_rate(off_before: pl.DataFrame, prior_season_rate: float) -> float:
    """League interceptions per dropback: the season to date once it has 300 dropbacks, else the
    previous season's rate."""
    dbs = off_before.filter(pl.col("qb_dropback").fill_null(0) == 1)
    if dbs.height >= LEAGUE_INT_MIN_DROPBACKS:
        return float((dbs["interception"].fill_null(0) == 1).mean())  # type: ignore[arg-type]
    return prior_season_rate


def _is_offense() -> pl.Expr:
    return (
        pl.col("play_type").is_in(["pass", "run"])
        & pl.col("epa").is_not_null()
        & pl.col("posteam").is_not_null()
    )


def _offense(plays: pl.DataFrame) -> pl.DataFrame:
    return plays.filter(_is_offense())


# ------------------------------------------------------------------------------------- efficiency


def _metric_exprs() -> list[pl.Expr]:
    """The seven efficiency aggregations, aliased by metric (shared by `_metrics` and the
    per-team league bands, so both give identical numbers)."""
    db = pl.col("qb_dropback").fill_null(0) == 1
    run = pl.col("play_type") == "run"
    yards = pl.col("yards_gained")
    explosive = (
        pl.when(yards.is_null())
        .then(None)
        .otherwise(((~run) & (yards >= 20)) | (run & (yards >= 10)))
        .cast(pl.Float64)
    )
    return [
        pl.col("epa").mean().alias("epa_play"),
        pl.col("success").mean().alias("success"),
        pl.col("epa").filter(db).mean().alias("epa_dropback"),
        pl.col("epa").filter(run & ~db).mean().alias("epa_rush"),
        explosive.mean().alias("explosive"),
        (pl.col("sack").fill_null(0).filter(db).sum() / db.sum()).alias("sack_rate"),
        pl.col("pass_oe").mean().alias("proe"),
    ]


def _clean(v: object) -> float | None:
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)  # type: ignore[arg-type]


def _metrics(df: pl.DataFrame) -> dict[str, float | None]:
    """The seven efficiency metrics over a frame of offensive plays (pass/run with epa)."""
    if df.is_empty():
        return dict.fromkeys(OFF_LABELS)
    r = df.select(_metric_exprs()).row(0, named=True)
    return {k: _clean(v) for k, v in r.items()}


LEAGUE_BAND_MIN_TEAMS = 8
LEAGUE_BAND_PCT = (10, 90)


def _league_bands(before: pl.DataFrame, col: str) -> dict[str, tuple[float | None, float | None]]:
    """Per metric, the 10th and 90th percentile (linear) of the teams' season-to-date values,
    grouping `before` by `col` (posteam for offense, defteam for defense)."""
    none = (None, None)
    if before.is_empty():
        return dict.fromkeys(OFF_LABELS, none)
    per_team = before.filter(pl.col(col).is_not_null()).group_by(col).agg(_metric_exprs())
    out: dict[str, tuple[float | None, float | None]] = {}
    for metric in OFF_LABELS:
        vals = [v for v in map(_clean, per_team[metric].to_list()) if v is not None]
        if len(vals) < LEAGUE_BAND_MIN_TEAMS:
            out[metric] = none
        else:
            lo, hi = np.percentile(vals, LEAGUE_BAND_PCT)
            out[metric] = (_round_metric(metric, float(lo)), _round_metric(metric, float(hi)))
    return out


def _round_metric(metric: str, v: float | None) -> float | None:
    if v is None:
        return None
    return _z(v, 1 if OFF_LABELS[metric][1] == "pp" else 3)


def _efficiency(off: pl.DataFrame, team: str, before: pl.DataFrame, gid: str) -> list[Efficiency]:
    """`off` = all offensive plays of the season; `before` = those of games kicked off earlier."""
    league = _metrics(before)
    n_games = {}
    out = []
    for side, col in (("off", "posteam"), ("def", "defteam")):
        game = _metrics(off.filter((pl.col("game_id") == gid) & (pl.col(col) == team)))
        prior = before.filter(pl.col(col) == team)
        n_games[side] = prior["game_id"].n_unique()
        season = _metrics(prior)
        bands = _league_bands(before, col)
        for metric, (label, unit) in OFF_LABELS.items():
            if side == "off":
                better = metric != "sack_rate"
            else:
                better = metric == "sack_rate"
            out.append(
                Efficiency(
                    metric=f"{side}_{metric}",
                    unit_side=side,  # type: ignore[arg-type]
                    label=label if side == "off" else DEF_LABELS[metric],
                    unit=unit,  # type: ignore[arg-type]
                    higher_is_better=better,
                    game=_round_metric(metric, game[metric]),
                    season=_round_metric(metric, season[metric]),
                    league=_round_metric(metric, league[metric]),
                    league_lo=bands[metric][0],
                    league_hi=bands[metric][1],
                    season_games=n_games[side],
                )
            )
    return out


# ------------------------------------------------------------------------------------------ luck


def _bucket_expr(col: str, buckets: list[Bucket], field_: str) -> pl.Expr:
    parts = [
        pl.when(_in_bucket(pl.col(col), b.lo, b.hi)).then(pl.lit(getattr(b, field_)))
        for b in buckets
    ]
    return pl.coalesce(parts).cast(pl.Float64)


DOWN_SPEC = (
    (3, "third_down_converted", "third_down_failed", "third_down"),
    (4, "fourth_down_converted", "fourth_down_failed", "fourth_down"),
)
ADJ_PRIOR_PLAYS = 50
RATE_CLIP = (0.02, 0.98)


def _is_go(down: int, conv: str, fail: str) -> pl.Expr:
    """A 3rd/4th-down go-for-it play the expectations count."""
    return (
        (pl.col("down") == down)
        & pl.col("play_type").is_in(["pass", "run"])
        & ((pl.col(conv) == 1) | (pl.col(fail) == 1))
        & pl.col("ydstogo").is_not_null()
        & (pl.col("interception").fill_null(0) != 1)  # turnovers are priced by their factors
        & (pl.col("fumble_lost").fill_null(0) != 1)
        & (pl.col("aborted_play").fill_null(0) != 1)
    )


def _go_plays(plays: pl.DataFrame, E: Expectations) -> pl.DataFrame:
    """3rd/4th-down go-for-it plays (the expectations filter) with `_down`, `_conv`, `_rate`
    (league bucket rate) and `_value` (bucket value)."""
    parts = []
    for down, conv, fail, attr in DOWN_SPEC:
        buckets = getattr(E, attr)
        df = plays.filter(_is_go(down, conv, fail))
        parts.append(
            df.with_columns(
                pl.lit(down).alias("_down"),
                (pl.col(conv) == 1).cast(pl.Float64).alias("_conv"),
                _bucket_expr("ydstogo", buckets, "rate").alias("_rate"),
                _bucket_expr("ydstogo", buckets, "value").alias("_value"),
            ).select("posteam", "defteam", "_down", "_conv", "_rate", "_value")
        )
    return pl.concat(parts)


def _excess(df: pl.DataFrame) -> float:
    """Conversions above the league bucket rates, per attempt, shrunk with 50 pseudo-attempts."""
    if df.is_empty():
        return 0.0
    return float((df["_conv"] - df["_rate"]).sum()) / (df.height + ADJ_PRIOR_PLAYS)


def _down_factors(
    game: pl.DataFrame, before: pl.DataFrame, team: str, opp: str, E: Expectations
) -> dict[int, tuple[float, float, int, float]]:
    """Per down: (actual, expected, attempts, swing) against a team-adjusted rate: the league
    bucket rate plus the offense's and the opponent defense's prior excess (3rd and 4th pooled)."""
    prior = _go_plays(before, E)
    adj = _excess(prior.filter(pl.col("posteam") == team)) + _excess(
        prior.filter(pl.col("defteam") == opp)
    )
    mine = _go_plays(game, E).filter(pl.col("posteam") == team)
    out = {}
    for down, *_ in DOWN_SPEC:
        df = mine.filter(pl.col("_down") == down)
        if df.is_empty():
            out[down] = (0.0, 0.0, 0, 0.0)
            continue
        rate = (pl.col("_rate") + adj).clip(*RATE_CLIP)
        r = df.select(
            pl.col("_conv").sum().alias("a"),
            rate.sum().alias("e"),
            ((pl.col("_conv") - rate) * pl.col("_value")).sum().alias("s"),
        ).row(0)
        out[down] = (float(r[0]), float(r[1]), df.height, float(r[2]))
    return out


def _is_fg() -> pl.Expr:
    return (
        (pl.col("field_goal_attempt") == 1)
        & pl.col("kick_distance").is_not_null()
        & (pl.col("field_goal_result").fill_null("") != "blocked")  # a special-teams big play
    )


def _is_xp() -> pl.Expr:
    return pl.col("extra_point_attempt") == 1


def _kicking(plays: pl.DataFrame, team: str, E: Expectations) -> tuple[float, float, int, float]:
    fg = plays.filter((pl.col("posteam") == team) & _is_fg()).with_columns(
        _bucket_expr("kick_distance", E.field_goal, "rate").alias("_rate"),
        _bucket_expr("kick_distance", E.field_goal, "value").alias("_value"),
        (pl.col("field_goal_result") == "made").cast(pl.Float64).alias("_made"),
    )
    xp = plays.filter((pl.col("posteam") == team) & _is_xp())
    xp_made = float((xp["extra_point_result"] == "good").sum())
    actual = float(fg["_made"].sum()) + xp_made
    expected = float(fg["_rate"].sum()) + xp.height * E.extra_point_rate
    swing = float(((fg["_made"] - fg["_rate"]) * fg["_value"]).sum())
    swing += (xp_made - xp.height * E.extra_point_rate) * 1.0
    return actual, expected, fg.height + xp.height, swing


def _is_big_play(team: str | None = None) -> pl.Expr:
    """Return TD on a kick/punt or a blocked punt/FG that benefits `team` (either team if None)."""
    scorer = pl.col("td_team") == team if team else pl.col("td_team").is_not_null()
    stopper = pl.col("defteam") == team if team else pl.col("defteam").is_not_null()
    ret = (pl.col("return_touchdown") == 1) & (pl.col("special_teams_play") == 1) & scorer
    blocked = ((pl.col("punt_blocked") == 1) | (pl.col("field_goal_result") == "blocked")) & stopper
    return ret | blocked


def _big_plays(plays: pl.DataFrame, team: str) -> int:
    """Return TDs on kicks/punts, blocked punts and blocked FGs that benefit `team`."""
    return plays.filter(_is_big_play(team)).height


def _penalty_yards(plays: pl.DataFrame, team: str | None = None) -> float:
    df = plays.filter((pl.col("penalty_yards") > 0) & pl.col("penalty_team").is_not_null())
    if team is not None:
        df = df.filter(pl.col("penalty_team") == team)
    return float(df["penalty_yards"].sum() or 0.0)


@dataclass
class _Ctx:
    """Everything the luck factors need for one game."""

    E: Expectations
    game: pl.DataFrame  # all plays of this game
    before: pl.DataFrame  # all plays of earlier games
    league_int_rate: float
    names: dict[str, str]


def _luck(ctx: _Ctx, team: str, opp: str, code: str) -> tuple[list[LuckFactor], float]:
    """Luck factors for `team` (canonical code); `code` is the games-table code for display."""
    E, g, b = ctx.E, ctx.game, ctx.before
    name = ctx.names.get(code, code)
    out: list[LuckFactor] = []

    def add(factor, label, actual, expected, unit, attempts, swing, sentence, partly=False):
        out.append(
            LuckFactor(
                factor=factor, label=label, actual=_z(actual, 2), expected=_z(expected, 2),
                unit=unit, attempts=attempts, swing_pts=_z(swing, 1), partly_skill=partly,
                sentence=sentence,
            )
        )  # fmt: skip

    off_g = _offense(g).filter(pl.col("posteam") == team)

    # fumbles
    fum = off_g.filter(pl.col("fumble") == 1)
    n_f = fum.height
    lost = float((fum["fumble_lost"].fill_null(0) == 1).sum())
    exp_f = _z(n_f * E.fumble_lost_share, 2)
    swing = -(lost - n_f * E.fumble_lost_share) * E.value_fumble_lost
    swing = _z(swing, 1)
    if n_f:
        s = (
            f"{name} lost {lost:.0f} of its {n_f} {_plural(n_f, 'fumble')}; about {exp_f:.1f} "
            f"would be lost on average ({_sig(swing)} pts)."
        )
    else:
        s = f"{name} did not fumble ({_sig(swing)} pts)."
    add("fumbles", "Fumble recoveries", lost, exp_f, "count", n_f, swing, s)

    # interceptions: shrunk season-to-date rate per dropback
    off_b = _offense(b)
    db_g = off_g.filter(pl.col("qb_dropback").fill_null(0) == 1)
    n_db = db_g.height
    ints = float((db_g["interception"].fill_null(0) == 1).sum())
    tb = off_b.filter((pl.col("posteam") == team) & (pl.col("qb_dropback").fill_null(0) == 1))
    t_db = tb.height
    t_int = float((tb["interception"].fill_null(0) == 1).sum())
    rate = (t_int + INT_PRIOR_DROPBACKS * ctx.league_int_rate) / (t_db + INT_PRIOR_DROPBACKS)
    exp_i = _z(n_db * rate, 2)
    swing = _z(-(ints - n_db * rate) * E.value_interception, 1)
    s = (
        f"{name} threw {ints:.0f} {_plural(ints, 'interception')} on {n_db} dropbacks; its rate "
        f"this season predicts {exp_i:.1f} ({_sig(swing)} pts)."
    )
    add("interceptions", "Interceptions thrown", ints, exp_i, "count", n_db, swing, s, True)

    # 3rd and 4th downs: expected for these two teams, not the league
    downs = _down_factors(g, b, team, opp, E)
    for factor, label, down, noun in (
        ("third_down", "3rd-down conversions", 3, "third down"),
        ("fourth_down", "4th-down conversions", 4, "fourth down"),
    ):
        a, e, n, sw = downs[down]
        e, sw = _z(e, 2), _z(sw, 1)
        if n:
            s = (
                f"{name} converted {a:.0f} of {n} {_plural(n, noun)}; {e:.1f} "
                f"{'were' if e != 1 else 'was'} expected from the {_plural(n, 'distance')} and "
                f"both teams' form this season ({_sig(sw)} pts)."
            )
        else:
            s = f"{name} had no {noun} tries that counted ({_sig(sw)} pts)."
        add(factor, label, a, e, "count", n, sw, s, True)

    # kicking
    a, e, n, sw = _kicking(g, team, E)
    e, sw = _z(e, 2), _z(sw, 1)
    if n:
        s = (
            f"{name} made {a:.0f} of {n} {_plural(n, 'kick')}; the league makes {e:.1f} from the "
            f"same {_plural(n, 'distance')} ({_sig(sw)} pts)."
        )
    else:
        s = f"{name} attempted no field goals or extra points ({_sig(sw)} pts)."
    add("kicking", "Field goals and extra points", a, e, "count", n, sw, s)

    # penalties
    yards = _penalty_yards(g, team)
    prior_games = b.filter((pl.col("posteam") == team) | (pl.col("defteam") == team))[
        "game_id"
    ].n_unique()
    if prior_games:
        exp_p = _penalty_yards(b, team) / prior_games
        basis = "its {e:.1f} a game this season"
    else:
        lg_games = b["game_id"].n_unique()
        exp_p = _penalty_yards(b) / (2 * lg_games) if lg_games else DEFAULT_PENALTY_YARDS
        basis = "the league's {e:.1f} a team-game"
    exp_p = _z(exp_p, 2)
    sw = _z(-(yards - exp_p) * E.value_penalty_yard, 1)
    s = f"{name} was penalized {yards:.0f} yards against {basis.format(e=exp_p)} ({_sig(sw)} pts)."
    add("penalties", "Penalty yards", yards, exp_p, "yards", None, sw, s, True)

    # special teams
    f_, ag = _big_plays(g, team), _big_plays(g, opp)
    exp_st = _z(E.special_teams_big_plays_pg, 2)
    sw = _z((f_ - ag) * E.value_special_teams_big_play, 1)
    if f_ == 0 and ag == 0:
        s = (
            f"{name} had no return touchdowns or blocked kicks either way; about {exp_st:.1f} a "
            f"game is normal ({_sig(sw)} pts)."
        )
    else:
        s = (
            f"{name} had {f_} return touchdowns or blocked kicks for it and {ag} against; about "
            f"{exp_st:.1f} a game is normal ({_sig(sw)} pts)."
        )
    add("special_teams", "Return TDs and blocked kicks", f_, exp_st, "count", None, sw, s)

    return out, _z(sum(x.swing_pts for x in out), 1)


# ------------------------------------------------------------------------------------ played like


def _played_like(
    E: Expectations, game_off: pl.DataFrame, g: dict, names: dict[str, str]
) -> PlayedLike:
    def team_epa(team: str) -> tuple[float, float]:
        df = game_off.filter(
            (pl.col("posteam") == _alias(team))
            & (pl.col("interception").fill_null(0) != 1)
            & (pl.col("fumble_lost").fill_null(0) != 1)
        )
        e, s = df["epa"].mean(), df["success"].mean()
        return (float(e) if e is not None else 0.0), (float(s) if s is not None else 0.0)  # type: ignore[arg-type]

    h_e, h_s = team_epa(g["home_team"])
    a_e, a_s = team_epa(g["away_team"])
    fit = E.played_like
    z = fit.intercept + fit.b_epa * (h_e - a_e) + fit.b_success * (h_s - a_s)
    p_home = round(_expit(z), 4)
    home_fav = _expit(z) >= 0.5  # decided on the unrounded value
    fav = g["home_team"] if home_fav else g["away_team"]
    p_fav = p_home if home_fav else round(1 - p_home, 4)
    margin = g["home_score"] - g["away_score"]
    hi, lo = max(g["home_score"], g["away_score"]), min(g["home_score"], g["away_score"])
    matches: bool | None
    if margin == 0:
        matches, tail = None, f"tied {hi}-{lo}"
    else:
        matches = (margin > 0) == home_fav
        tail = f"{'won' if matches else 'lost'} {hi}-{lo}"
    nm = names.get(fav, fav)
    sentence = (
        f"Teams that played as efficiently as {nm} did here (turnovers aside) win "
        f"{round(100 * p_fav):d}% of the time; {nm} {tail}."
    )
    return PlayedLike(
        p_home=p_home, favored=fav, matches_result=matches, sentence=sentence,
        home_epa=round(h_e, 3), away_epa=round(a_e, 3),
        home_success=round(h_s, 3), away_success=round(a_s, 3),
        p_base=round(_expit(fit.intercept), 4),
    )  # fmt: skip


# ----------------------------------------------------------------------------------- predictions


def _predictions(
    rows: pl.DataFrame, gid: str, margin: int, g: dict, reg: dict, groups: dict[str, str]
) -> tuple[list[GradedPick], str | None, list[Attribution]]:
    from nfl.features.groups import FEATURE_GROUP

    y = 1.0 if margin > 0 else (0.0 if margin < 0 else 0.5)
    picks: list[GradedPick] = []
    attrib: dict[str, Attribution] = {}
    if rows.is_empty():
        return [], None, []
    for r in rows.filter(pl.col("game_id") == gid).iter_rows(named=True):
        meta = reg.get(r["model_id"])
        if meta is None or r["p_home"] is None:
            continue
        p = float(r["p_home"])
        home = p >= 0.5
        sh = r["spread_home"]
        picks.append(
            GradedPick(
                model_id=r["model_id"],
                label=meta["label"],
                kind=meta["kind"],
                status=r["status"],
                p_home=round(p, 4),
                pick=g["home_team"] if home else g["away_team"],
                p_pick=round(p if home else 1 - p, 4),
                right=None if margin == 0 else (margin > 0) == home,
                log_loss=round(_ll(p, y), 4),
                spread_home=None if sh is None else _z(sh, 1),
                spread_error=None if sh is None else _z(abs(sh - margin), 1),
                best=False,
            )
        )
        if meta["kind"] in APPROACH_KINDS and r["contributions"]:
            attrib[r["model_id"]] = _attribution(r, meta, y, FEATURE_GROUP, groups)
    kind_rank = {"approach": 0, "ensemble": 1}
    picks.sort(key=lambda x: (kind_rank.get(x.kind, 2), x.log_loss, x.model_id))
    elig = [x for x in picks if x.kind in APPROACH_KINDS]
    best_id = None
    if elig:
        best = min(elig, key=lambda x: x.log_loss)
        best_id = best.model_id
        picks = [x.model_copy(update={"best": x.model_id == best_id}) for x in picks]
    order = sorted(attrib.values(), key=lambda a: (a.model_id == "ensemble", a.model_id))
    return picks, best_id, order


def _attribution(r: dict, meta: dict, y: float, feature_group: dict, groups: dict) -> Attribution:
    c = json.loads(r["contributions"])
    total = sum(c.values())
    by_group: dict[str, float] = {}
    for f, v in c.items():
        if f == "home_field":
            continue
        grp = feature_group.get(f, "other")
        by_group[grp] = by_group.get(grp, 0.0) + v
    base = _ll(_expit(total), y)
    out = []
    for grp, cg in by_group.items():
        pp = 100 * (_expit(total) - _expit(total - cg))
        out.append(
            GroupValue(
                group=grp,
                label=groups.get(grp, grp),
                pp=_z(pp, 1),
                value=_z(_ll(_expit(total - cg), y) - base, 4),
            )
        )
    out.sort(key=lambda x: (-x.value, x.group))
    top = out[0] if out and out[0].value > 0 else None
    return Attribution(
        model_id=r["model_id"],
        label=meta["label"],
        groups=out,
        most_valuable=top.group if top else None,
    )


# ------------------------------------------------------------------------------------------ phases

KICK_TYPES = ["kickoff", "punt", "field_goal", "extra_point"]


def _phase(
    phase: str, label: str, note: str, vals: dict[str, float | None], text: dict[str, str],
    higher_is_better: bool = True,
) -> Phase:  # fmt: skip
    """`vals` and `text` are keyed home and away. Two values that print the same are even."""
    h, a = vals["home"], vals["away"]
    leader = None
    if h is not None and a is not None and text["home"] != text["away"]:
        leader = "home" if (h > a) == higher_is_better else "away"
    return Phase(
        phase=phase, label=label, note=note, home=h, away=a,
        home_text=text["home"], away_text=text["away"], leader=leader,
    )  # fmt: skip


def _yard_line(y: float) -> str:
    r = round(y)
    return "midfield" if r == 50 else f"own {r}" if r < 50 else f"opp {100 - r}"


def _phases(game: pl.DataFrame, teams: dict[str, TeamRetro], home: str, away: str) -> list[Phase]:
    """Who won each part of the game. The first three reuse the efficiency rows, so the page shows
    one number for each; `game` is this game's plays, `home` and `away` the site's team codes."""
    sides = {"home": _alias(home), "away": _alias(away)}
    scrimmage = game.filter(
        pl.col("play_type").is_in(["pass", "run"]) & pl.col("posteam").is_not_null()
    )

    def efficiency(metric: str) -> dict[str, float | None]:
        return {s: next(e.game for e in teams[s].efficiency if e.metric == metric) for s in sides}

    def epa_text(v: float | None) -> str:
        return "–" if v is None else f"{v:+.2f}".replace("-", "−")

    pas, rush, big = (efficiency(m) for m in ("off_epa_dropback", "off_epa_rush", "off_explosive"))

    # the swing plays' own count (turnovers on the play left out), so the page says one number
    third_vals, third_text = {}, {}
    for s in sides:
        f = next((x for x in teams[s].luck if x.factor == "third_down"), None)
        made, tries = (int(f.actual), f.attempts or 0) if f else (0, 0)
        third_vals[s] = made / tries if tries else None
        third_text[s] = f"{made} of {tries}"

    zone_vals, zone_text = {}, {}
    for s, t in sides.items():
        inside = scrimmage.filter(
            (pl.col("posteam") == t)
            & (pl.col("yardline_100") <= 20)
            & pl.col("drive").is_not_null()
        )
        trips = inside["drive"].n_unique()
        scored = inside.filter((pl.col("touchdown") == 1) & (pl.col("td_team") == t))
        tds = scored["drive"].n_unique()
        zone_vals[s] = tds / trips if trips else None
        zone_text[s] = f"{tds} of {trips}" if trips else "no trips"

    # as `strength.st_epa_pg` counts it: kickoffs and punts both ways (returns against coverage),
    # field goals and extra points for the kicker alone. EPA is from the posteam's view.
    kicks = game.filter(
        ((pl.col("special_teams_play") == 1) | pl.col("play_type").is_in(KICK_TYPES))
        & pl.col("epa").is_not_null()
        & ~pl.col("play_type").is_in(["pass", "run"])
    )
    both_ways = kicks.filter(pl.col("play_type").is_in(["kickoff", "punt"]))
    st = {
        s: round(
            float(kicks.filter(pl.col("posteam") == t)["epa"].sum())
            - float(both_ways.filter(pl.col("defteam") == t)["epa"].sum()),
            2,
        )
        for s, t in sides.items()
    }

    # a drive's first scrimmage play, leaving out drives right after a turnover: otherwise this
    # row mostly repeats the turnovers row (.notes/ui/played-like-factors.md)
    drives = (
        scrimmage.filter(pl.col("drive").is_not_null() & pl.col("yardline_100").is_not_null())
        .sort("play_id")
        .group_by("drive", maintain_order=True)
        .agg(
            pl.col("posteam").first(),
            pl.col("yardline_100").first(),
            (pl.col("interception").fill_null(0) + pl.col("fumble_lost").fill_null(0))
            .sum()
            .alias("lost"),
        )
        .with_columns((pl.col("lost").shift(1).fill_null(0) > 0).alias("after_turnover"))
        .filter(~pl.col("after_turnover"))
    )
    field_vals, field_text = {}, {}
    for s, t in sides.items():
        starts = drives.filter(pl.col("posteam") == t)["yardline_100"]
        field_vals[s] = round(100 - float(starts.mean()), 1) if len(starts) else None
        field_text[s] = "–" if field_vals[s] is None else _yard_line(field_vals[s])

    lost = {}
    for s, t in sides.items():
        mine = scrimmage.filter(pl.col("posteam") == t)
        lost[s] = float(
            mine["interception"].fill_null(0).sum() + mine["fumble_lost"].fill_null(0).sum()
        )

    def pct_text(v: float | None) -> str:
        return "–" if v is None else f"{100 * v:.1f}%"

    return [
        _phase("passing", "Passing", "Expected points added per dropback.", pas, {s: epa_text(v) for s, v in pas.items()}),
        _phase("rushing", "Rushing", "Expected points added per rush.", rush, {s: epa_text(v) for s, v in rush.items()}),
        _phase("explosive", "Explosive plays", "Share of plays gaining 20+ yards passing or 10+ rushing.", big, {s: pct_text(v) for s, v in big.items()}),
        _phase("third_down", "Third downs", "Third downs converted, leaving out plays with a turnover.", third_vals, third_text),
        _phase("red_zone", "Red zone", "Touchdowns on drives that reached the opponent's 20.", zone_vals, zone_text),
        _phase("special_teams", "Special teams", "Expected points on kicks, punts and returns: kickoffs and punts for and against, field goals and extra points for the kicker.", st, {s: f"{v:+.1f}".replace("-", "−") for s, v in st.items()}),
        _phase("field_position", "Field position", "Average drive start, leaving out drives right after a turnover.", field_vals, field_text),
        _phase("turnovers", "Turnovers", "Interceptions and lost fumbles on offense. A fumbled return counts under special teams.", lost, {s: f"{v:.0f}" for s, v in lost.items()}, higher_is_better=False),
    ]  # fmt: skip


# ---------------------------------------------------------------------------------------- headlines


def pure_luck(t: TeamRetro) -> float:
    """Sum of the rounded swings of the factors that are not partly skill."""
    return _z(sum(f.swing_pts for f in t.luck if not f.partly_skill), 1)


def _swing_sentence(home: str, h: float, away: str, a: float, tail: str) -> str:
    """The swing-plays headline when the nets differ by a point or more. W is the team ahead on
    swing plays, L the team behind; the wording follows the signs (a net toward W can still mean
    both teams lost points)."""
    (w_name, w), (l_name, l) = sorted(((home, h), (away, a)), key=lambda t: -t[1])
    net = f"{_z(abs(h - a), 1):.1f}"
    if w < 0 and l < 0:
        return (
            f"Swing plays hurt both teams, {l_name} more: {_z(abs(l), 1):.1f} points lost "
            f"against {_z(abs(w), 1):.1f} for {w_name}, a net {net} toward {w_name}{tail}"
        )
    if w > 0 and l > 0:
        return (
            f"Swing plays helped both teams, {w_name} more: {_z(w, 1):.1f} points gained "
            f"against {_z(l, 1):.1f} for {l_name}, a net {net} toward {w_name}{tail}"
        )
    if w == 0:
        return (
            f"Swing plays cost {l_name} {_z(abs(l), 1):.1f} points and left {w_name} even, "
            f"a net {net} toward {w_name}{tail}"
        )
    if l == 0:
        return (
            f"Swing plays helped {w_name} by {_z(w, 1):.1f} points and left {l_name} even, "
            f"a net {net} toward {w_name}{tail}"
        )
    return (
        f"Swing plays helped {w_name} by {_z(w, 1):.1f} points and cost {l_name} "
        f"{_z(abs(l), 1):.1f}, a net {net} toward {w_name}{tail}"
    )


def _headlines(
    g: dict, names: dict[str, str], teams: dict[str, TeamRetro], pl_: PlayedLike
) -> list[str]:
    out = []
    home, away = g["home_team"], g["away_team"]
    nm = lambda c: names.get(c, c)

    factors = [f for side in ("home", "away") for f in teams[side].luck]
    top = max(factors, key=lambda f: abs(f.swing_pts))
    out.append(top.sentence)

    h, a = teams["home"].luck_net, teams["away"].luck_net
    hs, as_ = (pure_luck(teams[k]) for k in ("home", "away"))
    tail = f"; the pure-luck part was {_sig(hs)} for {nm(home)} and {_sig(as_)} for {nm(away)}."
    if abs(h - a) >= 1:
        out.append(_swing_sentence(nm(home), h, nm(away), a, tail))
    else:
        out.append(
            f"Swing plays roughly evened out ({_sig(h)} for {nm(home)}, {_sig(a)} for "
            f"{nm(away)}){tail}"
        )

    out.append(pl_.sentence)

    gaps = []
    for side, code in (("home", home), ("away", away)):
        e = next(x for x in teams[side].efficiency if x.metric == "off_epa_play")
        if e.season is not None and e.game is not None:
            gaps.append((abs(e.game - e.season), code, e))
    if gaps:
        _, code, e = max(gaps, key=lambda t: t[0])
        verb = "gained" if e.game >= 0 else "averaged"  # type: ignore[operator]
        rel = "above" if e.game >= e.season else "below"  # type: ignore[operator]
        n_ = nm(code)
        poss = n_ + ("'" if n_.endswith("s") else "'s")
        out.append(
            f"{poss} offense {verb} {e.game:.2f} EPA per play, {rel} its {e.season:.2f} "
            f"this season."
        )

    return out[:6]


# ---------------------------------------------------------------------------------------- builder


# ------------------------------------------------------------------------- win probability, drives

WP_NEEDS = {
    "vegas_home_wp",
    "vegas_home_wpa",
    "qtr",
    "game_seconds_remaining",
    "desc",
    "season_type",
}
DRIVE_NEEDS = {
    "fixed_drive", "fixed_drive_result", "drive_start_yard_line", "drive_end_yard_line",
    "drive_play_count", "qtr", "game_seconds_remaining", "season_type", "posteam", "play_type",
}  # fmt: skip
MARK_TYPES = ["pass", "run", "punt", "field_goal", "extra_point", "kickoff"]
DRIVE_TYPES = ["pass", "run", "punt", "field_goal", "kickoff", "qb_kneel", "qb_spike"]
MARK_MIN_WPA = 0.05
MARKS = 5
TEXT_MAX = 160
FACTOR_ORDER = ("interceptions", "fumbles", "special_teams", "kicking", "third_down", "fourth_down")


def _timeline(df: pl.DataFrame) -> pl.DataFrame:
    """Sort by play_id and add `_gsr` (seconds left, null filled from the previous row) and `_t`
    (elapsed game seconds). `game_seconds_remaining` counts the whole game down and overtime
    restarts it, so overtime adds the regulation and the earlier periods (10 minutes in the
    regular season, 15 in the playoffs). `_t` never decreases (a few rows run backwards)."""
    gsr = pl.col("game_seconds_remaining").cast(pl.Float64).forward_fill()
    qtr = pl.col("qtr").cast(pl.Float64)
    ot_len = pl.when(pl.col("season_type") == "POST").then(900).otherwise(600)
    t = pl.when(qtr >= 5).then(3600 + ot_len * (qtr - 5) + (ot_len - gsr)).otherwise(3600 - gsr)
    return (
        df.sort("play_id", nulls_last=True, maintain_order=True)
        .with_columns(gsr.alias("_gsr"))
        .with_columns(t.round(0).cum_max().fill_null(0).cast(pl.Int64).alias("_t"))
    )


def _clock(qtr: int | None, gsr: float | None) -> str:
    """Time left in the quarter as m:ss."""
    left = 0 if gsr is None else round(gsr)
    if qtr is not None and qtr < 5:
        left -= 900 * (4 - qtr)
    left = max(left, 0)
    return f"{left // 60}:{left % 60:02d}"


def _trim(text: str | None) -> str:
    if not text or len(text) <= TEXT_MAX:
        return text or ""
    cut = text[:TEXT_MAX]
    if text[TEXT_MAX] != " " and " " in cut:  # mid-word: back up to the last space
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip()


def _factor_expr() -> pl.Expr:
    """The luck factor a play is counted in, from the predicates `_luck` uses (penalties are not
    tagged: they are priced per yard, not per play)."""
    dropback = _is_offense() & (pl.col("qb_dropback").fill_null(0) == 1)
    fumble = _is_offense() & (pl.col("fumble") == 1) & (pl.col("fumble_lost").fill_null(0) == 1)
    conds = {
        "interceptions": dropback & (pl.col("interception").fill_null(0) == 1),
        "fumbles": fumble,
        "special_teams": _is_big_play(),
        "kicking": _is_fg() | _is_xp(),
    }
    for down, conv, fail, attr in DOWN_SPEC:
        conds[attr] = _is_go(down, conv, fail)
    out = pl.when(conds[FACTOR_ORDER[0]]).then(pl.lit(FACTOR_ORDER[0]))
    for k in FACTOR_ORDER[1:]:
        out = out.when(conds[k]).then(pl.lit(k))
    return out.otherwise(None).alias("_factor")


def _code(posteam: str | None, g: dict) -> str | None:
    """The games-table code of the offense (posteam is canonical on load)."""
    if posteam is None:
        return None
    for code in (g["home_team"], g["away_team"]):
        if _alias(code) == posteam:
            return code
    return None


def _wp_series(game_plays: pl.DataFrame, g: dict) -> WpSeries | None:
    """The home win-probability curve and its turning points (ADR 0020); None when the plays lack
    the columns or the probabilities."""
    if not WP_NEEDS <= set(game_plays.columns) or g["home_score"] is None:
        return None
    df = _timeline(game_plays)
    if df["vegas_home_wp"].null_count() == df.height:
        return None
    # `play_id` order is not game order around a timeout: an icing timeout sorts after the kick and
    # repeats the stale probability. A play's value after it is wp + wpa, and the stale row has
    # wpa 0, so the curve takes only rows where the play changed the probability.
    after = (pl.col("vegas_home_wp") + pl.col("vegas_home_wpa")).clip(0, 1)
    df = df.with_columns(
        after.alias("_after"),
        _factor_expr(),
        pl.col("vegas_home_wp").drop_nulls().first().alias("_open"),
    )
    curve = df.filter((pl.col("vegas_home_wpa").fill_null(0) != 0) & pl.col("_after").is_not_null())

    marks: list[WpPlay] = []
    cand = curve.filter(pl.col("play_type").is_in(MARK_TYPES)).with_columns(
        pl.col("vegas_home_wp").round(3).alias("_pb"), pl.col("_after").round(3).alias("_pa")
    )
    cand = (
        cand.with_columns((pl.col("_pa") - pl.col("_pb")).round(3).alias("_w"))
        .filter(pl.col("_w").abs() >= MARK_MIN_WPA - 1e-9)
        .sort(pl.col("_w").abs(), "play_id", descending=[True, False])
        .head(MARKS)
    )
    for r in cand.iter_rows(named=True):
        qtr = int(r["qtr"]) if r["qtr"] is not None else min(r["_t"] // 900 + 1, 4)
        marks.append(
            WpPlay(
                play_id=int(r["play_id"]), t=r["_t"], qtr=qtr, clock=_clock(qtr, r["_gsr"]),
                team=_code(r["posteam"], g), p_before=_z(r["_pb"], 3), p_after=_z(r["_pa"], 3),
                wpa=_z(r["_w"], 3), factor=r["_factor"], text=_trim(r["desc"]),
            )
        )  # fmt: skip
    marked = {m.play_id for m in marks}

    points: list[tuple[int, float]] = [(0, _z(df["_open"][0], 3))]
    for r in curve.iter_rows(named=True):
        p = _z(r["_after"], 3)
        if p != points[-1][1] or int(r["play_id"]) in marked:  # a mark's point is always kept
            points.append((r["_t"], p))
    ot = bool((df["qtr"] >= 5).any())
    end_t = int(df.filter(pl.col("_gsr").is_not_null())["_t"].max() or 0) if ot else 3600
    hs, as_ = g["home_score"], g["away_score"]
    result = 1.0 if hs > as_ else 0.0 if hs < as_ else 0.5
    points.append((end_t, result))  # kept even when it repeats the last value
    if len(points) < 2:
        return None

    low = None
    if result != 0.5:
        view = [(t, _z(p if result == 1.0 else 1 - p, 3)) for t, p in points]
        low = min(view, key=lambda x: x[1])  # min keeps the earliest of equal values
    return WpSeries(
        model="nflfastr_vegas", points=points, end_t=end_t, ot=ot, plays=marks, winner_low=low
    )


def _own_yard(text: str | None, offense: str | None) -> int | None:
    """ "ARI 31" is the 31 when ARI has the ball and the 69 when it doesn't, "50" the 50: yards from
    the offense's own goal line."""
    if text is None:
        return None
    parts = text.split()
    try:
        if len(parts) == 1:
            return int(parts[0])
        if len(parts) == 2:
            n = int(parts[1])
            return n if _alias(parts[0]) == offense else 100 - n
    except ValueError:
        pass
    return None


def _drives(game_plays: pl.DataFrame, g: dict) -> list[Drive] | None:
    """One row per possession from nflverse's `fixed_drive`; the END GAME pseudo-drive (no real
    plays) is dropped. None when the plays lack the columns or no drive is left."""
    if not DRIVE_NEEDS <= set(game_plays.columns):
        return None
    df = _timeline(game_plays).filter(pl.col("fixed_drive").is_not_null())
    out: list[Drive] = []
    for _, d in df.group_by("fixed_drive", maintain_order=True):
        real = d.filter(pl.col("play_type").is_in(DRIVE_TYPES))
        if real.is_empty():
            continue
        # a kickoff's posteam is the kicking team, so prefer the other plays
        pos = d.filter(pl.col("play_type") != "kickoff")["posteam"].drop_nulls()
        pos = pos if len(pos) else d["posteam"].drop_nulls()
        offense = pos[0] if len(pos) else None
        code = _code(offense, g)
        if code is None:
            continue

        def first(col: str, d=d):
            v = d[col].drop_nulls()
            return v[0] if len(v) else None

        n_plays = first("drive_play_count")
        out.append(
            Drive(
                n=len(out) + 1, team=code, qtr=int(real["qtr"][0]), t0=int(real["_t"][0]),
                t1=int(real["_t"][-1]), start_yl=_own_yard(first("drive_start_yard_line"), offense),
                end_yl=_own_yard(first("drive_end_yard_line"), offense),
                plays=None if n_plays is None else int(n_plays), result=first("fixed_drive_result"),
            )
        )  # fmt: skip
    return out or None


@dataclass
class BuildReport:
    written: list[str] = field(default_factory=list)
    up_to_date: int = 0
    skipped: int = 0  # finished games with no curated plays
    weeks: set[int] = field(default_factory=set)  # weeks of the written games


def retro_path(paths: Paths, season: int, game_id: str) -> Path:
    return paths.marts / "retro" / f"season={season}" / f"{game_id}.json"


def _stamped(path: Path) -> dict | None:
    """The stored record's staleness stamps (pbp_hash, expectations_version, schema_version), None
    if unreadable."""
    try:
        d = json.loads(path.read_text())
    except OSError, ValueError:
        return None
    return {
        "pbp_hash": d.get("pbp_hash"),
        "expectations_version": d.get("expectations_version"),
        "schema_version": d.get("schema_version"),
    }


HASH_COLS = [c for c in PLAY_COLS if c != "raw_snapshot_ts"]


def plays_hash(game_plays: pl.DataFrame) -> str:
    """Stable hash of one game's plays (the columns the retro reads, sorted by play_id); a new
    nflverse snapshot with identical plays hashes the same."""
    cols = [c for c in HASH_COLS if c in game_plays.columns]
    csv = game_plays.sort("play_id", nulls_last=True).select(cols).write_csv()
    return hashlib.sha256(csv.encode()).hexdigest()[:32]


def build_game(
    g: dict, plays: pl.DataFrame, E: Expectations, rows: pl.DataFrame, ctx: dict, snap: str,
    built_at: datetime, pbp_hash: str | None = None,
) -> RetroGame:  # fmt: skip
    names = ctx["names"]
    gid = g["game_id"]
    home, away = g["home_team"], g["away_team"]
    kick = g["kickoff_utc"]
    in_game = pl.col("game_id") == gid
    before_ids = ctx["kickoff"].filter(pl.col("kickoff_utc") < kick)["game_id"].to_list()
    game_plays = plays.filter(in_game)
    before = plays.filter(pl.col("game_id").is_in(before_ids))
    off_all = _offense(plays.filter(in_game | pl.col("game_id").is_in(before_ids)))
    off_before = _offense(before)

    lr = league_int_rate(off_before, ctx["prior_int_rate"])
    lctx = _Ctx(E=E, game=game_plays, before=before, league_int_rate=lr, names=names)

    teams: dict[str, TeamRetro] = {}
    for side, code, opp, score in (
        ("home", home, away, g["home_score"]),
        ("away", away, home, g["away_score"]),
    ):
        luck, net = _luck(lctx, _alias(code), _alias(opp), code)
        teams[side] = TeamRetro(
            team=code,
            score=score,
            efficiency=_efficiency(off_all, _alias(code), off_before, gid),
            luck=luck,
            luck_net=net,
        )

    margin = g["home_score"] - g["away_score"]
    played = _played_like(E, off_all.filter(in_game), g, names)
    reg = ctx["registry"]
    picks, best_id, attribution = _predictions(rows, gid, margin, g, reg, ctx["groups"])
    headlines = _headlines(g, names, teams, played)
    return RetroGame(
        game_id=gid,
        season=int(g["season"]),
        week=int(g["week"]),
        kickoff_utc=_ts(kick),
        away=away,
        home=home,
        result=Result(home_score=g["home_score"], away_score=g["away_score"], margin=margin),
        built_at=_ts(built_at),
        pbp_snapshot_ts=snap,
        pbp_hash=pbp_hash,
        expectations_version=E.version,
        headlines=headlines,
        played_like=played,
        phases=_phases(game_plays, teams, home, away),
        teams=teams,  # type: ignore[arg-type]
        predictions=picks,
        best_model=best_id,
        attribution=attribution,
        wp_series=_wp_series(game_plays, g),
        drives=_drives(game_plays, g),
    )


def _with_market(rows: pl.DataFrame, market: pl.DataFrame) -> pl.DataFrame:
    """Replace any `market_baseline` rows with the game page's market (status = its source)."""
    if market.is_empty():
        return rows
    mk = market.filter(pl.col("p_home").is_not_null()).select(
        "game_id",
        pl.lit("market_baseline").alias("model_id"),
        "p_home",
        "spread_home",
        pl.lit(None, dtype=pl.Utf8).alias("contributions"),
        pl.lit(None, dtype=pl.Datetime("us")).alias("lock_ts"),
        pl.col("source").cast(pl.Utf8).alias("status"),
    )
    if rows.is_empty():
        return mk
    keep = rows.filter(pl.col("model_id") != "market_baseline").select(mk.columns)
    return pl.concat([keep, mk], how="vertical_relaxed")


def build(
    paths: Paths,
    season: int,
    week: int | None = None,
    game_ids: list[str] | None = None,
    force: bool = False,
) -> BuildReport:
    from nfl import site

    if not expectations_path(paths).exists():
        raise FileNotFoundError(
            f"{expectations_path(paths)} is missing: run `nfl retro expectations` first"
        )
    E = load(paths)
    report = BuildReport()
    games = _load_games(paths, season)
    finished = games.filter(pl.col("result").is_not_null())
    if week is not None:
        finished = finished.filter(pl.col("week") == week)
    if game_ids:
        finished = finished.filter(pl.col("game_id").is_in(game_ids))
    if finished.is_empty():
        return report

    plays = _load_plays(paths, season)
    snaps = plays.group_by("game_id").agg(pl.col("raw_snapshot_ts").max().alias("snap"))
    snap_of = dict(zip(snaps["game_id"], snaps["snap"], strict=True))

    hashes = {
        gid[0]: plays_hash(part)
        for gid, part in plays.partition_by("game_id", as_dict=True).items()
    }
    todo = []
    for g in finished.sort("kickoff_utc", "game_id").iter_rows(named=True):
        gid = g["game_id"]
        snap = snap_of.get(gid)
        if snap is None:
            report.skipped += 1
            continue
        stamped = _stamped(retro_path(paths, season, gid))
        stale = (
            stamped is None
            or stamped["pbp_hash"] != hashes[gid]
            or stamped["expectations_version"] != E.version
            or stamped["schema_version"] != SCHEMA_VERSION
        )
        if force or stale:
            todo.append((g, snap))
        else:
            report.up_to_date += 1
    if not todo:
        return report

    now = now_utc().replace(tzinfo=None, microsecond=0)
    rows = site.display_rows(paths, games, now)
    # a game with no lock or backfill always gets its approaches scored as of kickoff - 1h,
    # whatever the week window display_rows applies
    have = (
        rows.select("game_id").unique()
        if not rows.is_empty()
        else pl.DataFrame(schema={"game_id": pl.Utf8})
    )
    missing = [g["game_id"] for g, _ in todo if g["game_id"] not in set(have["game_id"])]
    if missing:
        extra = site.pregame_rows(paths, games, have, now, game_ids=missing)
        if not extra.is_empty():
            cols = ["game_id", "model_id", "p_home", "spread_home", "contributions", "lock_ts", "status"]  # fmt: skip
            rows = pl.concat(
                [r.select(cols) for r in (rows, extra) if not r.is_empty()], how="vertical_relaxed"
            )
    rows = _with_market(rows, site.market_rows(paths, games, now))
    ctx = {
        "names": _names(),
        "registry": site.model_registry(),
        "groups": {x["id"]: x["name"] for x in site.groups_meta()["groups"]},
        "kickoff": games.select("game_id", "kickoff_utc"),
        "prior_int_rate": _prior_league_int_rate(paths, season),
    }
    for g, snap in todo:
        rec = build_game(g, plays, E, rows, ctx, snap, now, hashes[g["game_id"]])
        out = retro_path(paths, season, g["game_id"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rec.model_dump(mode="json"), indent=1) + "\n")
        report.written.append(g["game_id"])
        report.weeks.add(int(g["week"]))
    return report


def build_games(
    paths: Paths,
    season: int | None = None,
    week: int | None = None,
    game_ids: list[str] | None = None,
    force: bool = False,
) -> list[str]:
    """Write the retros that are missing or stale; returns the written game ids."""
    return build(paths, season or current_season(), week, game_ids, force).written
