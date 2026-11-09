"""The player value model (ADR 0027, M24.2): point-in-time, scaled to the priors, sane on real data."""

import polars as pl

from nfl.players import priors as P
from nfl.players import value as V

from .conftest import requires_data


def _games(rows):
    """Player-games: (season, week, gsis, team, grp, share, x, n)."""
    return pl.DataFrame(
        [{"season": s, "week": w, "game_type": "REG", "team": t, "gsis_id": g, "player": g,
          "grp": grp, "share": sh, "x": x, "n": n} for s, w, g, t, grp, sh, x, n in rows],
        schema_overrides={"x": pl.Float64, "n": pl.Float64, "share": pl.Float64},
    )  # fmt: skip


BASE = [
    (2025, 1, "a", "AAA", "WR", 0.9, 5.0, 1.0),
    (2025, 2, "a", "AAA", "WR", 0.9, 5.0, 1.0),
    (2025, 1, "b", "BBB", "WR", 0.9, 0.0, 1.0),
    (2025, 2, "b", "BBB", "WR", 0.9, 0.0, 1.0),
]


def test_as_of_reads_only_games_before_the_week():
    pg = _games(BASE + [(2025, 3, "a", "AAA", "WR", 0.9, 50.0, 1.0)])
    before = V.as_of(pg, 2025, 3)
    a = before.filter(pl.col("gsis_id") == "a").row(0, named=True)
    assert (a["wx"], a["wn"], a["games"]) == (10.0, 2.0, 2)  # week 3's 50 is not in it
    after = V.as_of(pg, 2025, 4).filter(pl.col("gsis_id") == "a").row(0, named=True)
    assert after["wx"] == 60.0


def test_a_planted_week_never_changes_that_weeks_value():
    prior = pl.DataFrame(schema={"gsis_id": pl.Utf8, "season": pl.Int64, "apy_cap_pct": pl.Float64,
                                 "rookie": pl.Boolean, "draft_pick": pl.Int64})  # fmt: skip
    clean = _games(BASE)
    planted = _games(BASE + [(2025, 3, "b", "BBB", "WR", 0.9, 99.0, 1.0)])
    v1 = V.score(V.as_of(clean, 2025, 3), {"WR": 1.0}, prior)
    v2 = V.score(V.as_of(planted, 2025, 3), {"WR": 1.0}, prior)
    key = ["gsis_id", "value_pts"]
    assert v1.sort("gsis_id").select(key).equals(v2.sort("gsis_id").select(key))


def test_earlier_seasons_count_less():
    pg = _games(
        [(2024, 1, "a", "AAA", "WR", 0.9, 4.0, 1.0), (2025, 1, "a", "AAA", "WR", 0.9, 4.0, 1.0)]
    )
    a = V.as_of(pg, 2025, 2).row(0, named=True)
    assert a["wx"] == 4.0 + P.SEASON_DECAY * 4.0
    assert a["wn"] == 1.0 + P.SEASON_DECAY


def test_a_player_gone_for_two_seasons_is_left_out():
    pg = _games([(2023, 1, "old", "AAA", "WR", 0.9, 4.0, 1.0)] + BASE)
    assert "old" not in V.as_of(pg, 2025, 3)["gsis_id"].to_list()


def test_the_multiplier_maps_replacement_to_zero_and_top_to_one():
    prior = pl.DataFrame(schema={"gsis_id": pl.Utf8, "season": pl.Int64, "apy_cap_pct": pl.Float64,
                                 "rookie": pl.Boolean, "draft_pick": pl.Int64})  # fmt: skip
    rows = [(2025, 1, f"p{i}", "AAA", "WR", 0.9, float(i), 1.0) for i in range(20)]
    v = V.score(V.as_of(_games(rows), 2025, 2), {"WR": 0.0}, prior).sort("production")
    assert v["multiplier"][0] == 0.0  # the worst regular is below replacement
    assert v["multiplier"][-1] <= P.MAX_MULTIPLIER
    top = v.filter(pl.col("quality_pct") >= P.TOP_PCT)["value_pts"]
    assert (top >= P.TOP_STARTER_POINTS["WR"] * 0.99 * min(1.0, 0.9 / P.FULL_ROLE)).all()


def test_role_scales_a_part_timer_down():
    prior = pl.DataFrame(schema={"gsis_id": pl.Utf8, "season": pl.Int64, "apy_cap_pct": pl.Float64,
                                 "rookie": pl.Boolean, "draft_pick": pl.Int64})  # fmt: skip
    rows = [(2025, 1, "full", "AAA", "WR", 0.9, 5.0, 1.0), (2025, 1, "part", "AAA", "WR", 0.35, 5.0, 1.0),
            (2025, 1, "low", "AAA", "WR", 0.9, 0.0, 1.0)]  # fmt: skip
    v = V.score(V.as_of(_games(rows), 2025, 2), {"WR": 0.0}, prior)
    full = v.filter(pl.col("gsis_id") == "full")["value_pts"].item()
    part = v.filter(pl.col("gsis_id") == "part")["value_pts"].item()
    assert part == full * (0.35 / P.FULL_ROLE)


def test_rookie_deals_rank_by_draft_slot_below_a_top_veteran():
    g = pl.DataFrame({
        "apy_cap_pct": [0.12, 0.02, 0.01, None], "rookie": [False, False, True, True],
        "draft_pick": [100, 200, 1, 260],
    })  # fmt: skip
    pct = V._prior_pct(g).to_list()
    assert pct[0] > pct[1]  # veterans by cap share
    assert pct[2] == V.ROOKIE_TOP and pct[3] == V.ROOKIE_LAST
    assert pct[2] < 1.0


@requires_data
def test_real_values_are_in_the_published_range():
    from nfl.config import get_paths

    df = pl.read_parquet(V.out_path(get_paths())).filter(
        (pl.col("season") == 2025) & (pl.col("week") == 10)
    )
    top = df.group_by("grp").agg(pl.col("value_pts").max().alias("top"))
    tops = dict(zip(top["grp"].to_list(), top["top"].to_list(), strict=True))
    assert 4.0 <= tops["QB"] <= 7.5
    for g in ("WR", "TE", "RB", "OL", "EDGE", "CB", "S"):
        assert 0.4 <= tops[g] <= 2.0, g
    # one row per player per week
    assert df.select("gsis_id").is_unique().all()


def test_group_means_use_a_fixed_window_whatever_the_build_loads():
    rows = [(s, 1, f"p{s}", "AAA", "WR", 0.9, float(s - 2000), 1.0) for s in range(2010, 2026)]
    pg = _games(rows)
    full = V.group_means(pg, 2025)
    short = V.group_means(pg.filter(pl.col("season") >= 2025 - P.SEASONS_BACK), 2025)
    assert full == short


@requires_data
def test_a_one_season_build_equals_the_full_build():
    from nfl.config import get_paths

    paths = get_paths()
    one = V.build_values(paths, (2025, 2025)).filter(pl.col("week") == 10)
    full = pl.read_parquet(V.out_path(paths)).filter(
        (pl.col("season") == 2025) & (pl.col("week") == 10)
    )
    k = ["gsis_id", "value_pts"]
    assert one.sort("gsis_id").select(k).equals(full.sort("gsis_id").select(k))
