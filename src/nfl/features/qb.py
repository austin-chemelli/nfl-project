"""Quarterback features for the strength family: `strength.qb_epa` and `strength.qb_cpoe`.

These follow the quarterback, not the team. For every (game, team):

* Projected starter. Completed games: the team's **first** passer of that game (lowest play_id
  with a dropback), i.e. the starter, which is known before kickoff. (v1 used the passer with the
  most dropbacks; that leaked in-game injuries and benchings into a pregame feature in ~3% of
  team-games, and made the Sharp look better than the market. Found 2026-10-27.) Upcoming games
  (and completed ones without play data): the starter of the team's previous game.
* Career rate before the game, strictly earlier games only, across any team he played for. Seasons
  are weighted 0.75 ** seasons_ago (the current season counts 1), applied to sums and counts:
      value = (sum w*x + n0 * replacement) / (sum w*n + n0),   n0 = 250 dropbacks
  `qb_epa` uses `qb_epa` (nflfastR EPA credited to the QB) on his dropbacks; `qb_cpoe` uses cpoe
  where it exists (null for every play before 2006 in our extract and for a share of pass plays
  after: no air yards), so a QB with no CPOE history sits exactly at replacement level.
* Replacement level for season S: pooled mean over seasons < S of the QBs whose career dropbacks
  through S - 1 are below 250 (backups, busts, rookies who haven't earned a job). Needs at least
  `MIN_REPL_N` observations, else the fallback (-0.10 EPA per dropback, -3.0 CPOE points).
"""

from __future__ import annotations

import warnings

import polars as pl

from nfl.models.elo import TEAM_ALIASES

N0_DROPBACKS = 250.0
SEASON_DECAY = 0.75
MIN_CAREER_FOR_REPL = 250.0
MIN_REPL_N = 100.0
FALLBACK_EPA = -0.10
FALLBACK_CPOE = -3.0

_STATS = ["n_db", "sx_e", "n_e", "sx_c", "n_c"]


def _canon(col: str) -> pl.Expr:
    return pl.col(col).replace(TEAM_ALIASES)


def asof_strictly_before(left: pl.DataFrame, right: pl.DataFrame, by: list[str]) -> pl.DataFrame:
    """Attach the latest `right` row per `by` group with kickoff_utc strictly before the left row's
    (both frames sorted by kickoff_utc; polars can't verify sortedness with `by`, hence the
    explicit sort and the muted warning)."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Sortedness of columns cannot be checked")
        return left.sort("kickoff_utc").join_asof(
            right.sort("kickoff_utc"),
            on="kickoff_utc",
            by=by,
            strategy="backward",
            allow_exact_matches=False,
        )


def _per_game(plays: pl.DataFrame) -> pl.DataFrame:
    """One row per (game_id, ckey, qb): dropbacks and EPA / CPOE sums and counts."""
    return (
        plays.filter((pl.col("qb_dropback") == 1) & pl.col("passer_player_id").is_not_null())
        .with_columns(_canon("posteam").alias("ckey"), pl.col("passer_player_id").alias("qb"))
        .group_by("game_id", "ckey", "qb")
        .agg(
            pl.len().cast(pl.Float64).alias("n_db"),
            pl.col("qb_epa").sum().alias("sx_e"),
            pl.col("qb_epa").count().cast(pl.Float64).alias("n_e"),
            pl.col("cpoe").sum().alias("sx_c"),
            pl.col("cpoe").count().cast(pl.Float64).alias("n_c"),
        )
    )


def projected_starters(tg: pl.DataFrame, plays: pl.DataFrame) -> pl.DataFrame:
    """(game_id, team, ckey, qb, qb_name) per team-game; qb null when the team has no history."""
    # the starter: the team's first dropback of the game (pregame knowledge, not in-game outcome)
    if "play_id" not in plays.columns:  # synthetic frames: rows are already in play order
        plays = plays.with_row_index("play_id")
    actual = (
        plays.filter((pl.col("qb_dropback") == 1) & pl.col("passer_player_id").is_not_null())
        .with_columns(_canon("posteam").alias("ckey"))
        .sort("game_id", "play_id", maintain_order=True)
        .group_by("game_id", "ckey", maintain_order=True)
        .agg(pl.col("passer_player_id").first().alias("_act"))
    )
    names = (
        plays.filter(pl.col("passer_player_id").is_not_null())
        .group_by(pl.col("passer_player_id").alias("qb"))
        .agg(pl.col("passer_player_name").drop_nulls().last().alias("qb_name"))
    )
    out = (
        tg.sort("ckey", "kickoff_utc", "game_id", nulls_last=True)
        .join(actual, on=["game_id", "ckey"], how="left")
        .with_columns(
            pl.coalesce(pl.col("_act"), pl.col("_act").forward_fill().shift(1).over("ckey")).alias(
                "qb"
            )
        )
        .join(names, on="qb", how="left")
    )
    return out.select("game_id", "team", "ckey", "season", "kickoff_utc", "qb", "qb_name")


def _replacement(qs: pl.DataFrame, seasons: list[int]) -> pl.DataFrame:
    rows = []
    for s in seasons:
        career = (
            qs.filter(pl.col("season") < s)
            .group_by("qb")
            .agg(pl.col(c).sum() for c in _STATS)
            .filter(pl.col("n_db") < MIN_CAREER_FOR_REPL)
        )
        t = career.select(pl.col(c).sum() for c in _STATS).row(0, named=True)
        e = t["sx_e"] / t["n_e"] if (t["n_e"] or 0) >= MIN_REPL_N else FALLBACK_EPA
        c = t["sx_c"] / t["n_c"] if (t["n_c"] or 0) >= MIN_REPL_N else FALLBACK_CPOE
        rows.append((s, float(e), float(c)))
    return pl.DataFrame(
        rows,
        schema={"season": pl.Int64, "_re": pl.Float64, "_rc": pl.Float64},
        orient="row",
    )


def compute(tg: pl.DataFrame, plays: pl.DataFrame) -> pl.DataFrame:
    """Long (game_id, team, feature, value). `tg`: game_id, team, ckey, season, kickoff_utc."""
    st = projected_starters(tg, plays)
    pg = _per_game(plays)
    gk = tg.select("game_id", "season", "kickoff_utc").unique("game_id")
    qg = pg.group_by("game_id", "qb").agg(pl.col(c).sum() for c in _STATS).join(gk, on="game_id")
    qs = qg.group_by("qb", "season").agg(pl.col(c).sum() for c in _STATS)

    # current season to date: cumulative inclusive per (qb, season), as-of strictly before kickoff
    cur_tbl = (
        qg.sort("kickoff_utc")
        .with_columns(pl.col(c).cum_sum().over("qb", "season").alias(f"cur_{c}") for c in _STATS)
        .select("qb", "season", "kickoff_utc", *[f"cur_{c}" for c in _STATS])
    )
    tgt = st.filter(pl.col("qb").is_not_null()).sort("kickoff_utc")
    tgt = asof_strictly_before(tgt, cur_tbl, by=["qb", "season"])

    # earlier seasons, decayed
    pairs = tgt.select("qb", "season").unique()
    dec = (
        pairs.join(qs.rename({"season": "s0"}), on="qb")
        .filter(pl.col("s0") < pl.col("season"))
        .with_columns((SEASON_DECAY ** (pl.col("season") - pl.col("s0"))).alias("_w"))
        .group_by("qb", "season")
        .agg((pl.col(c) * pl.col("_w")).sum().alias(f"old_{c}") for c in _STATS)
    )
    tgt = tgt.join(dec, on=["qb", "season"], how="left").join(
        _replacement(qs, sorted(tgt["season"].unique().to_list())), on="season", how="left"
    )

    def tot(c: str) -> pl.Expr:
        return pl.col(f"cur_{c}").fill_null(0.0) + pl.col(f"old_{c}").fill_null(0.0)

    tgt = tgt.with_columns(
        ((tot("sx_e") + N0_DROPBACKS * pl.col("_re")) / (tot("n_e") + N0_DROPBACKS)).alias(
            "strength.qb_epa"
        ),
        ((tot("sx_c") + N0_DROPBACKS * pl.col("_rc")) / (tot("n_c") + N0_DROPBACKS)).alias(
            "strength.qb_cpoe"
        ),
    )
    feats = ["strength.qb_epa", "strength.qb_cpoe"]
    wide = st.select("game_id", "team").join(
        tgt.select("game_id", "team", *feats), on=["game_id", "team"], how="left"
    )
    return wide.unpivot(
        feats, index=["game_id", "team"], variable_name="feature", value_name="value"
    )
