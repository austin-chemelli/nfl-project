"""Form features: recent results of each team before the target game (architecture §3.3).

`form.last3_win_pct`, `form.last3_margin`, `form.streak` use only the team's completed games that
kicked off strictly before the target game, across season boundaries (postseason included).
Franchise relocations are folded together for the lookback (OAK->LV, SD->LAC, STL->LA); rows are
keyed by the team code printed on the target game.

Schedule-context features (M1.12) use only past results plus the published schedule (known in
advance): `epa_trend`, `ats_l3` (form), `off_bye`, `short_week`, `road_streak` (rest & travel),
`lookahead`, `letdown`, `eliminated`, `clinched` (stakes). Lookahead may read the *schedule* of the
next game, never its result; Elo ratings come from `nfl.models.elo.pregame_ratings`, which is
walk-forward (a game's rating never depends on its own or later results).
"""

from __future__ import annotations

from datetime import datetime

import polars as pl

from nfl.config import Paths
from nfl.features import store
from nfl.features.strength import load_plays
from nfl.models.elo import TEAM_ALIASES, pregame_ratings

SOURCE = "schedules"
VERSION = "3"
WINDOW = 3
LEAGUE_MEAN_ELO = 1505.0  # Elo regression target (EloParams.mean)
_BASE = ("last3_win_pct", "last3_margin", "streak")
_NEW = (
    "epa_trend", "ats_l3", "off_bye", "short_week", "road_streak",
    "lookahead", "letdown", "eliminated", "clinched",
)  # fmt: skip
FEATURES = tuple("form." + n for n in _BASE + _NEW)

TREND_WINDOW = 4
ATS_WINDOW = 3
BYE_DAYS = 13
SHORT_DAYS = 4
TOP_N = 8
ELIM_PCT = 0.35
CLINCH_PCT = 0.80
LATE_WEEK = 13
PRIMETIME_HOUR_ET = 19
THU, MON = 4, 1  # polars dt.weekday: Monday = 1


def _team_long(games: pl.DataFrame) -> pl.DataFrame:
    """One row per (game, team): game_id, team (as printed), franchise, kickoff, margin."""
    g = games.filter(pl.col("kickoff_utc").is_not_null()).select(
        "game_id",
        pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us")).alias("kickoff"),
        "home_team",
        "away_team",
        (pl.col("home_score") - pl.col("away_score")).alias("hm"),
        pl.col("result"),
        pl.col("season").cast(pl.Int64),
        pl.col("week").cast(pl.Int64),
        "game_type",
        (pl.col("location") != "Home").fill_null(False).alias("neutral"),
        pl.col("div_game").cast(pl.Boolean).fill_null(False).alias("div_game"),
        pl.col("spread_line").cast(pl.Float64).alias("spread"),
    )
    shared = ["season", "week", "game_type", "neutral", "div_game"]
    home = g.select(
        "game_id", "kickoff", *shared,
        pl.col("home_team").alias("team"), pl.col("away_team").alias("opp"),
        pl.col("hm").alias("margin"), pl.lit(True).alias("is_home"),
        pl.col("spread").alias("line"),
    )  # fmt: skip
    away = g.select(
        "game_id", "kickoff", *shared,
        pl.col("away_team").alias("team"), pl.col("home_team").alias("opp"),
        (-pl.col("hm")).alias("margin"), pl.lit(False).alias("is_home"),
        (-pl.col("spread")).alias("line"),
    )  # fmt: skip
    played = g.select("game_id", pl.col("result").is_not_null().alias("played"))
    out = pl.concat([home, away]).join(played, on="game_id")
    return out.with_columns(
        pl.col("team").replace(TEAM_ALIASES).alias("franchise"),
        pl.col("opp").replace(TEAM_ALIASES).alias("opp_franchise"),
        # unplayed games have no score; guard against a result without scores too
        pl.when(pl.col("played")).then(pl.col("margin")).alias("margin"),
    )


def _net_epa(plays: pl.DataFrame) -> pl.DataFrame:
    """(game_id, franchise, net_epa): offensive EPA/play minus defensive EPA/play allowed."""
    if plays.is_empty():
        return pl.DataFrame(
            schema={"game_id": pl.Utf8, "franchise": pl.Utf8, "net_epa": pl.Float64}
        )
    off = plays.group_by("game_id", pl.col("posteam").replace(TEAM_ALIASES).alias("franchise")).agg(
        pl.col("epa").mean().alias("off")
    )
    dfn = plays.group_by("game_id", pl.col("defteam").replace(TEAM_ALIASES).alias("franchise")).agg(
        pl.col("epa").mean().alias("dfn")
    )
    return off.join(dfn, on=["game_id", "franchise"], how="inner").select(
        "game_id", "franchise", (pl.col("off") - pl.col("dfn")).alias("net_epa")
    )


def _elo_context(long: pl.DataFrame, games: pl.DataFrame) -> pl.DataFrame:
    """Adds opp_elo (opponent's pre-game Elo), opp_rank (its Elo rank among all franchises at this
    kickoff, 1 = best) and next_opp_elo (the team's next scheduled opponent's latest pre-game
    rating at or before this kickoff) to the long frame."""
    r = pregame_ratings(games)
    e = pl.concat(
        [
            long.filter(pl.col("is_home")).join(
                r.select("game_id", pl.col("home_elo").alias("elo")), on="game_id"
            ),
            long.filter(~pl.col("is_home")).join(
                r.select("game_id", pl.col("away_elo").alias("elo")), on="game_id"
            ),
        ]
    ).select("game_id", "franchise", "kickoff", "elo")
    opp_elo = e.select(
        "game_id", pl.col("franchise").alias("opp_franchise"), pl.col("elo").alias("opp_elo")
    )
    long = long.join(opp_elo, on=["game_id", "opp_franchise"], how="left")

    # rank of every franchise at every distinct kickoff (latest pre-game rating at/before it)
    es = e.sort("kickoff")
    grid = (
        long.select("kickoff").unique().join(long.select("franchise").unique(), how="cross")
    ).sort("kickoff")
    at = grid.join_asof(
        es.select("franchise", pl.col("kickoff").alias("e_at"), "elo"),
        left_on="kickoff",
        right_on="e_at",
        by="franchise",
        strategy="backward",
        check_sortedness=False,
    ).drop_nulls("elo")
    at = at.with_columns(pl.col("elo").rank("min", descending=True).over("kickoff").alias("rank"))
    long = long.join(
        at.select(
            "kickoff", pl.col("franchise").alias("opp_franchise"), pl.col("rank").alias("opp_rank")
        ),
        on=["kickoff", "opp_franchise"],
        how="left",
    )

    nxt = (
        long.select("game_id", "franchise", "kickoff", "next_opp")
        .drop_nulls("next_opp")
        .sort("kickoff")
        .join_asof(
            es.select(
                pl.col("franchise").alias("next_opp"),
                pl.col("kickoff").alias("e_at"),
                pl.col("elo").alias("next_opp_elo"),
            ),
            left_on="kickoff",
            right_on="e_at",
            by="next_opp",
            strategy="backward",
            check_sortedness=False,
        )
        .select("game_id", "franchise", "next_opp_elo")
    )
    return long.join(nxt, on=["game_id", "franchise"], how="left")


def compute(games: pl.DataFrame, plays: pl.DataFrame) -> pl.DataFrame:
    """(game_id, team, feature, value) for every form feature."""
    long = _team_long(games)
    fr = "franchise"

    done = (
        long.filter(pl.col("played") & pl.col("margin").is_not_null())
        .sort(fr, "kickoff", "game_id")
        .with_columns(
            pl.col("margin").sign().cast(pl.Int64).alias("s"),
        )
        .with_columns(
            ((pl.col("s") + 1) / 2).alias("win"),  # win 1, tie 0.5, loss 0
            (pl.col("s") != pl.col("s").shift(1).over(fr))
            .fill_null(True)
            .cum_sum()
            .over(fr)
            .alias("run"),
        )
        .with_columns(
            (pl.col("s") * pl.int_range(pl.len()).over(fr, "run").add(1)).alias("streak"),
            pl.col("win").rolling_mean(WINDOW, min_samples=1).over(fr).alias("last3_win_pct"),
            pl.col("margin").rolling_mean(WINDOW, min_samples=1).over(fr).alias("last3_margin"),
        )
        .select(fr, pl.col("kickoff").alias("done_at"), "last3_win_pct", "last3_margin", "streak")
    )
    # ATS: cover rate over the last 3 games that had a line, across seasons
    ats = (
        long.filter(
            pl.col("played") & pl.col("margin").is_not_null() & pl.col("line").is_not_null()
        )
        .sort(fr, "kickoff", "game_id")
        .with_columns((((pl.col("margin") - pl.col("line")).sign() + 1) / 2).alias("cover"))
        .with_columns(
            pl.col("cover").rolling_mean(ATS_WINDOW, min_samples=1).over(fr).alias("ats_l3")
        )
        .select(fr, pl.col("kickoff").alias("ats_at"), "ats_l3")
    )

    base = long.join(_net_epa(plays), on=["game_id", fr], how="left").sort(fr, "kickoff", "game_id")
    base = base.with_columns(
        pl.col("opp_franchise").shift(-1).over(fr).alias("next_opp"),
        pl.col("season").shift(-1).over(fr).alias("next_season"),
        pl.col("game_type").shift(-1).over(fr).alias("next_type"),
    ).with_columns(
        pl.when(
            (pl.col("game_type") == "REG")
            & (pl.col("next_type") == "REG")
            & (pl.col("next_season") == pl.col("season"))
        )
        .then(pl.col("next_opp"))
        .alias("next_opp")
    )
    base = _elo_context(base, games).sort(fr, "kickoff", "game_id")

    et = pl.col("kickoff").dt.replace_time_zone("UTC").dt.convert_time_zone("America/New_York")
    reg = pl.col("game_type") == "REG"
    win = pl.col("played") & (pl.col("margin") > 0)
    primetime = (et.dt.hour() >= PRIMETIME_HOUR_ET) | et.dt.weekday().is_in([THU, MON])
    trigger = win & ((pl.col("opp_rank") <= TOP_N) | (pl.col("div_game") & primetime))
    road = (~pl.col("is_home")) | pl.col("neutral")
    # regular-season win share counting only played regular-season games
    w = pl.when(reg & pl.col("played")).then((pl.col("margin").sign() + 1) / 2)
    base = base.with_columns(
        et.dt.date().alias("et_date"),
        trigger.alias("trigger"),
        road.alias("road"),
        w.alias("w"),
    ).with_columns(
        (pl.col("et_date") - pl.col("et_date").shift(1).over(fr)).dt.total_days().alias("gap"),
        (pl.col("season") == pl.col("season").shift(1).over(fr)).alias("same_prev"),
        (~pl.col("road")).cum_sum().over(fr, "season").alias("home_cnt"),
        pl.col("w")
        .fill_null(0)
        .cum_sum()
        .over(fr, "season")
        .shift(1)
        .over(fr, "season")
        .alias("wsum"),
        pl.col("w")
        .is_not_null()
        .cast(pl.Int64)
        .cum_sum()
        .over(fr, "season")
        .shift(1)
        .over(fr, "season")
        .alias("wn"),
        pl.col("net_epa")
        .rolling_mean(TREND_WINDOW, min_samples=1)
        .over(fr, "season")
        .shift(1)
        .over(fr, "season")
        .alias("n4"),
        pl.col("net_epa")
        .fill_null(0)
        .cum_sum()
        .over(fr, "season")
        .shift(1)
        .over(fr, "season")
        .alias("nsum"),
        pl.col("net_epa")
        .is_not_null()
        .cast(pl.Int64)
        .cum_sum()
        .over(fr, "season")
        .shift(1)
        .over(fr, "season")
        .alias("nn"),
        pl.col("trigger").shift(1).over(fr).alias("prev_trigger"),
    )
    pct = pl.col("wsum") / pl.col("wn")
    late = reg & (pl.col("week") >= LATE_WEEK) & (pl.col("wn") > 0)
    base = base.with_columns(
        (pl.col("same_prev") & (pl.col("gap") >= BYE_DAYS))
        .fill_null(False)
        .cast(pl.Float64)
        .alias("off_bye"),
        (pl.col("same_prev") & (pl.col("gap") <= SHORT_DAYS))
        .fill_null(False)
        .cast(pl.Float64)
        .alias("short_week"),
        pl.col("road")
        .cast(pl.Int64)
        .cum_sum()
        .over(fr, "season", "home_cnt")
        .cast(pl.Float64)
        .alias("road_streak"),
        # v2 (2026-10-27): the next opponent's strength relative to an average team. v1 subtracted
        # this week's opponent's Elo, which made the feature mostly "this opponent is weak" (a
        # duplicate of team strength that fit with the wrong sign), not a look-ahead effect.
        (pl.col("next_opp_elo") - LEAGUE_MEAN_ELO).fill_null(0.0).alias("lookahead"),
        (pl.col("same_prev") & pl.col("prev_trigger"))
        .fill_null(False)
        .cast(pl.Float64)
        .alias("letdown"),
        (late & (pct < ELIM_PCT)).cast(pl.Float64).alias("eliminated"),
        (late & (pct > CLINCH_PCT)).cast(pl.Float64).alias("clinched"),
        pl.when(pl.col("nn") >= 2)
        .then(pl.col("n4") - pl.col("nsum") / pl.col("nn"))
        .otherwise(0.0)
        .fill_null(0.0)  # upcoming games right after unplayed ones have no rolling window
        .alias("epa_trend"),
    )

    # Stats after each completed game, attached to every later game of the franchise (strictly
    # earlier kickoff only, so the target game itself never contributes).
    target = base.select("game_id", "team", fr, "kickoff").sort("kickoff")
    joined = (
        target.join_asof(
            done.sort("done_at"),
            left_on="kickoff",
            right_on="done_at",
            by=fr,
            strategy="backward",
            allow_exact_matches=False,
            check_sortedness=False,
        )
        .with_columns(pl.col("streak").fill_null(0))
        .join_asof(
            ats.sort("ats_at"),
            left_on="kickoff",
            right_on="ats_at",
            by=fr,
            strategy="backward",
            allow_exact_matches=False,
            check_sortedness=False,
        )
        .join(
            base.select("game_id", "team", *[n for n in _NEW if n not in ("ats_l3",)]),
            on=["game_id", "team"],
        )
    )
    cols = [n for n in FEATURES]
    cols = [c.removeprefix("form.") for c in cols]
    values = joined.select("game_id", "team", *cols).unpivot(
        index=["game_id", "team"], variable_name="feature", value_name="value"
    )
    return values.with_columns(("form." + pl.col("feature")).alias("feature"))


def build(paths: Paths, games: pl.DataFrame, build_ts: datetime) -> pl.DataFrame:
    plays = load_plays(paths, int(games["season"].min()))
    values = compute(games, plays)
    return store.from_team_values(values, games, source=SOURCE, version=VERSION, build_ts=build_ts)
