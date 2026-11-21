"""The matchup feature family (ADR 0028, M25.9): parity with the engine, point in time, nulls."""

from datetime import datetime, timedelta

import polars as pl
import pytest

from nfl import matchups as M
from nfl.features import matchup, store

from .test_matchups import frame, unit_rows

SEASON = 2022
T0 = datetime(2022, 9, 8)
BUILD = datetime(2030, 1, 1)
TEAMS = ("AAA", "BBB", "CCC", "DDD")
SPLITS = ("blitz", "play_action")  # one defense-chosen, one offense-chosen edge split


def games_frame(weeks=range(1, 7)) -> pl.DataFrame:
    rows = []
    for w in weeks:
        pairs = [("AAA", "BBB"), ("CCC", "DDD")] if w % 2 else [("BBB", "CCC"), ("DDD", "AAA")]
        for h, a in pairs:
            rows.append((f"{SEASON}_{w:02d}_{h}", SEASON, w, T0 + timedelta(days=7 * w), h, a))
    return pl.DataFrame(
        rows,
        schema=["game_id", "season", "week", "kickoff_utc", "home_team", "away_team"],
        orient="row",
    )


def split_model(week4_scale: float = 1.0) -> pl.DataFrame:
    """Weeks 1-5 of the same pairings, every unit in both splits, numbers varying by team/week.
    `week4_scale` multiplies week 4's EPA (the mutation)."""
    rows = []
    games = games_frame(range(1, 6))
    for g in games.iter_rows(named=True):
        w = g["week"]
        for t_i, team in enumerate((g["home_team"], g["away_team"])):
            ti = TEAMS.index(team)
            scale = week4_scale if w == 4 else 1.0
            for si, split in enumerate(SPLITS):
                for side in ("off", "def"):
                    n1 = 12 + 3 * ti + si + (4 if side == "def" else 0)
                    e1 = scale * (0.05 * (ti + 1) - 0.03 * w + 0.02 * si) * n1
                    e0 = scale * (0.01 * (3 - ti) + 0.01 * w) * 40
                    rows += unit_rows(SEASON, w, g["game_id"], team, side, split, n1, e1, 40, e0)
    return frame(rows)


def feat(vals: pl.DataFrame, gid: str, team: str, name: str):
    r = vals.filter(
        (pl.col("game_id") == gid) & (pl.col("team") == team) & (pl.col("feature") == name)
    )
    assert r.height == 1
    return r["value"][0]


def test_parity_with_the_engine_and_home_minus_away_convention():
    df, games = split_model(), games_frame()
    vals = matchup.compute(games, df)
    e = M.Engine(df)
    for g in games.filter(pl.col("week").is_between(3, 5)).iter_rows(named=True):
        edges = e.matchup_edges(g)
        home_rows = {r.split: r.edge_pts_pg for r in edges.sides[0].rows if r.has_edge}
        away_rows = {r.split: r.edge_pts_pg for r in edges.sides[1].rows if r.has_edge}
        net = 0.0
        for s in ("blitz", "play_action"):
            want = home_rows[s] - away_rows[s]
            assert want is not None
            assert feat(vals, g["game_id"], g["home_team"], f"matchup.edge_{s}") == pytest.approx(
                want
            )
            assert feat(vals, g["game_id"], g["away_team"], f"matchup.edge_{s}") == pytest.approx(
                -want
            )
            net += want
        # FTN splits we did not plant have no rows: null on both sides, left out of the sum
        assert feat(vals, g["game_id"], g["home_team"], "matchup.edge_motion") is None
        assert feat(vals, g["game_id"], g["home_team"], "matchup.net_edge_pg") == pytest.approx(net)
        assert feat(vals, g["game_id"], g["away_team"], "matchup.net_edge_pg") == pytest.approx(
            -net
        )
        assert abs(net) > 1e-6


def test_null_before_week_three():
    vals = matchup.compute(games_frame(), split_model())
    for g in games_frame().filter(pl.col("week") < 3).iter_rows(named=True):
        for t in (g["home_team"], g["away_team"]):
            for name in matchup.FEATURES:
                assert feat(vals, g["game_id"], t, name) is None
    assert feat(vals, "2022_03_CCC", "CCC", "matchup.net_edge_pg") is not None


def test_only_edge_splits_have_features():
    assert "matchup.edge_shotgun" not in matchup.FEATURES  # context only
    assert "matchup.edge_third_down" not in matchup.FEATURES  # neither unit chooses
    assert "matchup.edge_blitz" in matchup.FEATURES


def test_mutation_leakage():
    games = games_frame()
    base = matchup.compute(games, split_model())
    mut = matchup.compute(games, split_model(week4_scale=5.0))
    for g in games.filter(pl.col("week") <= 4).iter_rows(named=True):  # week 4 sees weeks < 4
        for t in (g["home_team"], g["away_team"]):
            for name in matchup.FEATURES:
                a, b = feat(base, g["game_id"], t, name), feat(mut, g["game_id"], t, name)
                assert a == b or a == pytest.approx(b), (g["game_id"], t, name)
    assert feat(base, "2022_05_CCC", "CCC", "matchup.net_edge_pg") != pytest.approx(
        feat(mut, "2022_05_CCC", "CCC", "matchup.net_edge_pg")
    )


def test_store_rows_have_home_away_sides():
    games = games_frame()
    rows = store.from_team_values(
        matchup.compute(games, split_model()),
        games,
        source=matchup.SOURCE,
        version=matchup.VERSION,
        build_ts=BUILD,
    )
    store.validate(rows)
    assert rows.height == games.height * 2 * len(matchup.FEATURES)
    assert set(rows["side"]) == {"home", "away"}
    assert set(rows["source"]) == {"ftn"}
