"""The matchup engine (ADR 0028, M25.1): shrinkage, edges, point-in-time reads, reliability badges."""

from datetime import datetime

import numpy as np
import polars as pl
import pytest

from nfl import matchups as M
from nfl import splits
from nfl.config import get_paths

from .conftest import requires_data
from .synth import play
from .test_team_split_week import SEASON, build, gid

SCHEMA = {
    "season": pl.Int64, "week": pl.Int32, "game_id": pl.String, "team": pl.String,
    "side": pl.String, "split": pl.String, "flag": pl.Boolean, "plays": pl.Int64,
    "epa_sum": pl.Float64, "success_sum": pl.Float64, "explosive": pl.Int64,
}  # fmt: skip


def frame(rows) -> pl.DataFrame:
    """(season, week, game_id, team, side, split, flag, plays, epa_sum) tuples as the model's frame."""
    return pl.DataFrame(
        [(*r, 0.0, 0) for r in rows], schema=list(SCHEMA), orient="row"
    ).cast(SCHEMA)  # fmt: skip


def unit_rows(season, week, game, team, side, split, n1, e1, n0, e0):
    out = []
    if n1:
        out.append((season, week, game, team, side, split, True, n1, e1))
    if n0:
        out.append((season, week, game, team, side, split, False, n0, e0))
    return out


def league_gap(df: pl.DataFrame, side: str, split: str) -> float:
    d = df.filter((pl.col("side") == side) & (pl.col("split") == split))
    w, wo = d.filter(pl.col("flag")), d.filter(~pl.col("flag"))
    return w["epa_sum"].sum() / w["plays"].sum() - wo["epa_sum"].sum() / wo["plays"].sum()


def blitz_frame():
    """2022 weeks 1-3: offenses O1..O5 and defenses D1..D5 in blitz. O1 (the gap owner) was never
    blitzed; D1 blitzes 30%. Everyone else varies a little."""
    rows = []
    for w in (1, 2, 3):
        for i in range(1, 6):
            g = f"g{w}_{i}"
            n1 = 0 if i == 1 else 20 + i
            e1 = 0.1 * n1 - 0.02 * i * n1  # EPA with
            rows += unit_rows(SEASON, w, g, f"O{i}", "off", "blitz", n1, e1, 50, 0.05 * 50 * i / 5)
            n1d = 15 if i == 1 else 20 + i  # D1 blitzes 30 / 100
            rows += unit_rows(
                SEASON, w, g, f"D{i}", "def", "blitz", n1d, 0.1 * n1d, 35 if i == 1 else 50, 2.0
            )
    return frame(rows)


def test_n_zero_gives_league_gap_and_exact_edge():
    df = blitz_frame()
    e = M.Engine(df)
    o1 = e.unit_split(SEASON, 4, "O1", "off", "blitz")
    assert o1.n_with == 0 and o1.n == 0 and o1.weight == 0
    lg = league_gap(df.filter(pl.col("week") < 4), "off", "blitz")
    assert o1.league_gap == pytest.approx(lg)
    assert o1.shrunk_gap == pytest.approx(lg)  # exactly the league gap
    # blitz is defense-chosen: D1's habit against what O1 has faced, times O1's gap and plays/game
    d1 = e.unit_split(SEASON, 4, "D1", "def", "blitz")
    game = {"season": SEASON, "week": 4, "home_team": "O1", "away_team": "D1"}
    row = next(r for r in e.matchup_edges(game).sides[0].rows if r.split == "blitz")
    assert row.opp_rate == pytest.approx(d1.rate) and row.rate_faced == 0.0
    assert row.edge_pts_pg == pytest.approx((d1.rate - 0.0) * lg * o1.plays_pg)
    assert row.edge_pts_pg == pytest.approx((15 / 50) * lg * 50)
    assert row.favours in ("offense", "defense") and row.has_edge


def test_planted_team_residual_is_shrunk_by_n_over_n_plus_k():
    df = blitz_frame()
    u = M.Engine(df).unit_split(SEASON, 4, "O3", "off", "blitz")
    assert u.k == M.K_DEFAULT  # no earlier season has the split
    resid = u.raw_gap - u.league_gap
    assert abs(resid) > 0.01
    n = u.n_with * u.n_without / (u.n_with + u.n_without)
    assert (u.shrunk_gap - u.league_gap) / resid == pytest.approx(n / (n + u.k))
    assert u.weight == pytest.approx(n / (n + u.k))


def test_k_by_method_of_moments_on_earlier_seasons_clamped():
    rows = []
    gaps = []
    for i in range(24):  # 2021: 24 offenses, 800 plays split evenly, gaps spread out
        gap = 0.06 * (i - 11.5) / 11.5
        gaps.append(gap)
        rows += unit_rows(
            2021, 1, f"x{i}", f"T{i}", "off", "blitz", 400, 400 * gap / 2, 400, -400 * gap / 2
        )
    df = frame(rows + unit_rows(2022, 1, "y", "T1", "off", "blitz", 10, 0.0, 10, 0.0))
    e = M.Engine(df)
    d = np.array(gaps) - np.mean(gaps)
    tau2 = np.var(d, ddof=1) - M.SIGMA2 / 200
    expect = np.clip(M.SIGMA2 / tau2, M.K_MIN, M.K_MAX) if tau2 > 0 else M.K_MAX
    assert e.k(2022, "off", "blitz") == pytest.approx(expect)
    assert e.k(2021, "off", "blitz") == M.K_DEFAULT  # no earlier season
    assert e.k(2022, "def", "blitz") == M.K_DEFAULT  # the side has no earlier data

    def season_2021(gap_of):
        rows = [
            r
            for i in range(24)
            for r in unit_rows(
                2021, 1, f"x{i}", f"T{i}", "off", "blitz", 400, 400 * gap_of(i), 400, 0.0
            )
        ]
        return frame(rows + unit_rows(2022, 1, "y", "T1", "off", "blitz", 10, 0.0, 10, 0.0))

    # no spread beyond sampling noise -> the cap; a wide spread -> the floor
    assert M.Engine(season_2021(lambda i: 0.0)).k(2022, "off", "blitz") == M.K_MAX
    wide = season_2021(lambda i: np.linspace(-1, 1, 24)[i])
    assert M.Engine(wide).k(2022, "off", "blitz") == M.K_MIN


def test_neither_splits_get_unit_numbers_but_no_edge():
    df = blitz_frame()
    game = {"season": SEASON, "week": 4, "home_team": "O1", "away_team": "D1"}
    rows = M.matchup_edges(game, df).sides[0].rows
    assert [r.split for r in rows] == splits.ids()
    third = next(r for r in rows if r.split == "third_down")
    assert not third.has_edge and third.edge_pts_pg is None and "no edge" in third.note


def planted(week, epa, flag_blitz=2.0):
    base = {
        "season": SEASON,
        "week": week,
        "game_id": gid(week, "T01"),
        "posteam": "T01",
        "defteam": "T12",
    }
    return [
        play(**base, play_id=1.0, epa=epa, wp=0.5, down=1.0, n_blitzers=flag_blitz, n_pass_rushers=5.0,
             air_yards=20.0, yards_gained=25.0, yardline_100=15.0, shotgun=1.0),
        play(**base, play_id=2.0, epa=-1.0, wp=0.9, down=3.0, n_blitzers=0.0, n_pass_rushers=4.0,
             air_yards=5.0, yards_gained=5.0, yardline_100=60.0, shotgun=0.0),
    ]  # fmt: skip


def snapshot(df, week):
    e = M.Engine(df)
    game = {"season": SEASON, "week": week, "home_team": "T01", "away_team": "T12"}
    return [e.unit_splits(SEASON, week, t, s) for t in ("T01", "T12") for s in ("off", "def")], (
        e.matchup_edges(game).to_dict()
    )


def test_mutation_leakage(tmp_path):
    base = build(tmp_path / "a", planted(5, 1.0) + planted(4, 0.3), planted_game=(5, "T01"))
    # (week 4's planted game replaces the filler too: build the week-4 plays on top of the filler)
    same_w5 = build(
        tmp_path / "b", planted(5, -3.0, 0.0) + planted(4, 0.3), planted_game=(5, "T01")
    )
    prev_w4 = build(tmp_path / "c", planted(5, 1.0) + planted(4, 2.5), planted_game=(5, "T01"))
    a, b, c = (snapshot(x, 5) for x in (base, same_w5, prev_w4))
    assert a == b  # changing week-5 plays leaves every week-5 value unchanged
    assert a != c  # control: changing a week-4 play changes something
    # and the next week does see the week-5 change
    assert snapshot(base, 6) != snapshot(same_w5, 6)


def test_ftn_splits_absent_before_charting_and_k_default(tmp_path):
    df = build(tmp_path, planted(5, 1.0), planted_game=(5, "T01"))
    e = M.Engine(df)
    # 2022 week 1: nothing earlier, every unit has no rows and no gap
    for u in e.unit_splits(SEASON, 1, "T01", "off"):
        assert u.n_with == u.n_without == 0 and u.shrunk_gap is None and u.rate is None
    edges = e.matchup_edges({"season": SEASON, "week": 1, "home_team": "T01", "away_team": "T12"})
    assert all(r.edge_pts_pg is None for s in edges.sides for r in s.rows)
    # a split with no data before the week (the synthetic fillers have no FTN columns)
    for s in ("blitz", "play_action", "motion"):
        assert e.unit_split(SEASON, 4, "T01", "off", s).shrunk_gap is None
        assert e.k(SEASON, "off", s) == M.K_DEFAULT


def test_historical_team_codes_map_to_current():
    df = frame(unit_rows(2022, 1, "g", "LV", "off", "shotgun", 10, 1.0, 10, 0.0))
    assert M.Engine(df).unit_split(2022, 2, "OAK", "off", "shotgun").n_with == 10


def test_reliability_thresholds_and_missing_ledger():
    assert M.reliability("blitz") == "noise"
    assert M.reliability("blitz", pl.DataFrame()) == "noise"
    t0, t1 = datetime(2026, 11, 1), datetime(2026, 11, 8)
    ledger = pl.DataFrame(
        {
            "candidate": ["split_blitz_gap", "split_blitz_gap", "split_motion_gap", "split_rpo_gap",
                          "split_screen_gap", "split_box_light_gap", "split_deep_pass_gap"],
            "run_at": [t0, t1, t1, t1, t1, t1, t1],
            "split_half": [0.9, -0.08, 0.31, 0.1, 0.099, 0.3, None],
        }
    )  # fmt: skip
    assert M.reliability("blitz", ledger) == "noise"  # the latest row (-0.08) counts, not 0.9
    assert M.reliability("motion", ledger) == "stable"
    assert M.reliability("rpo", ledger) == "some"
    assert M.reliability("screen", ledger) == "noise"
    assert M.reliability("box_light", ledger) == "stable"  # >= 0.3 is stable
    assert M.reliability("deep_pass", ledger) == "noise"  # no split-half r
    assert M.reliability("shotgun", ledger) == "noise"  # no row
    game = {"season": SEASON, "week": 4, "home_team": "O1", "away_team": "D1"}
    rows = M.matchup_edges(game, blitz_frame(), ledger=ledger).sides[0].rows
    assert {r.split: r.reliability for r in rows}["motion"] == "stable"


def test_records_serialize():
    d = M.matchup_edges({"season": SEASON, "week": 4, "home_team": "O1", "away_team": "D1"},
                        blitz_frame()).to_dict()  # fmt: skip
    assert d["sides"][0]["rows"][0]["offense"]["split"] == "blitz"


# ---- real data: the GB at NE brief ----------------------------------------------------------

PARQUET = get_paths().marts / "derived" / "team_split_week.parquet"


@requires_data
@pytest.mark.skipif(not PARQUET.exists(), reason="needs the built team_split_week model")
def test_gb_at_ne_2026_week_9_reproduces_the_brief():
    df = pl.read_parquet(PARQUET)
    if df.filter((pl.col("season") == 2026) & (pl.col("week") == 8)).is_empty():
        pytest.skip("no 2026 Week 8 in the local data")
    e = M.Engine(df)
    ne = e.unit_rank(2026, 9, "NE", "off")
    gb = e.unit_rank(2026, 9, "GB", "def")
    assert (ne.rank, gb.rank, ne.of) == (9, 7, 32)
    faced = e.opponents_faced(2026, 9, "NE", "off")
    assert abs(faced["mean_epa_pp"] - ne.league_epa_pp) < 0.01  # league-average defenses
    game = {"season": 2026, "week": 9, "home_team": "NE", "away_team": "GB"}
    edges = e.matchup_edges(game)
    assert [(s.offense, s.defense) for s in edges.sides] == [("NE", "GB"), ("GB", "NE")]
    assert any(r.edge_pts_pg is not None for s in edges.sides for r in s.rows)
