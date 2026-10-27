"""Front builder: FTN-based tendencies as of the game's week; null before 2022."""

from datetime import datetime, timedelta

import duckdb
import polars as pl
import pytest

from nfl.features import front, store
from nfl.tendencies import N0, weekly_aggregates
from tests.conftest import DATA, requires_data
from tests.test_decisions import P, make_plays, write_plays

T0 = datetime(2021, 9, 10, 17, 0)
BUILD = datetime(2023, 9, 1)

# (id, season, week, days after T0, home, away)
SCHEDULE = [
    ("g1", 2021, 1, 0, "A", "B"),  # no FTN charting
    ("g2", 2022, 1, 365, "A", "B"),
    ("g3", 2022, 2, 372, "B", "A"),
    ("g4", 2022, 3, 379, "A", "B"),
]


def games_frame():
    return pl.DataFrame(
        {
            "game_id": [s[0] for s in SCHEDULE],
            "season": [s[1] for s in SCHEDULE],
            "week": [s[2] for s in SCHEDULE],
            "kickoff_utc": [T0 + timedelta(days=s[3]) for s in SCHEDULE],
            "home_team": [s[4] for s in SCHEDULE],
            "away_team": [s[5] for s in SCHEDULE],
            "result": [1.0] * len(SCHEDULE),
        }
    )


def ftn(gid, season, week, off, deff, play_type, *, motion=False, pa=False, blitz=0, box=7):
    d = play_type == "pass"
    return P(
        gid, season, week, off, deff, play_type=play_type, has_ftn=True, is_motion=motion,
        is_play_action=pa, n_blitzers=blitz, n_defense_box=box, qb_dropback=int(d),
        **{"pass": int(d)},
    )  # fmt: skip


def plays(g3_extra=()):
    r = [  # 2021: plays without FTN data, which must not feed any rate
        P("g1", 2021, 1, "A", "B", play_type="pass", down=1, **{"pass": 1}),
        P("g1", 2021, 1, "B", "A", play_type="run", down=1, **{"pass": 0}),
    ]
    # g2 (2022 wk1): A offense: 4 pass/run plays, 3 motion; 2 passes, 1 play action;
    # B defense faces 2 dropbacks, 1 blitzed; box >= 8 on 1 of 2 runs
    r += [
        ftn("g2", 2022, 1, "A", "B", "pass", motion=True, pa=True, blitz=1),
        ftn("g2", 2022, 1, "A", "B", "pass", motion=True, blitz=0),
        ftn("g2", 2022, 1, "A", "B", "run", motion=True, box=8),
        ftn("g2", 2022, 1, "A", "B", "run", box=6),
        # B offense: 4 plays, 1 motion; 1 pass without play action; A defense blitzes it
        ftn("g2", 2022, 1, "B", "A", "pass", motion=True, blitz=2),
        ftn("g2", 2022, 1, "B", "A", "run", box=9),
        ftn("g2", 2022, 1, "B", "A", "run", box=9),
        ftn("g2", 2022, 1, "B", "A", "run", box=5),
        P("g2", 2022, 1, "A", "B", play_type="punt", has_ftn=True, is_motion=True),  # excluded
    ]
    r += [ftn("g3", 2022, 2, "B", "A", "pass", motion=True, pa=True, blitz=3)] + list(g3_extra)
    r += [ftn("g4", 2022, 3, "A", "B", "pass", pa=True)]
    return r


def run(tmp_path, rows):
    paths = write_plays(tmp_path, make_plays(rows))
    weekly = weekly_aggregates(duckdb.connect(), paths, [2021, 2022], ["all"])
    return front.compute(games_frame(), weekly), paths


def feat(vals, gid, team, name):
    r = vals.filter(
        (pl.col("game_id") == gid) & (pl.col("team") == team) & (pl.col("feature") == name)
    )
    assert r.height == 1, (gid, team, name)
    return r["value"][0]


def shrunk(sx, n, league):
    return (sx + N0 * league) / (n + N0)


def test_null_before_2022_and_week1(tmp_path):
    vals, _ = run(tmp_path, plays())
    assert vals.height == 4 * 2 * 4  # a row per team-game-feature, nulls included
    for gid in ("g1", "g2"):  # 2021 has no FTN data; 2022 week 1 has no prior
        sub = vals.filter(pl.col("game_id") == gid)
        assert sub["value"].null_count() == sub.height
    assert vals.filter(pl.col("game_id").is_in(["g3", "g4"]))["value"].null_count() == 0


def test_rates_as_of_week(tmp_path):
    vals, _ = run(tmp_path, plays())
    # g3 (week 2) sees week 1 only; weight 1; prior = league rate over week 1
    motion_lg = (3 + 1) / 8
    assert feat(vals, "g3", "A", "front.motion_rate") == pytest.approx(shrunk(3, 4, motion_lg))
    assert feat(vals, "g3", "B", "front.motion_rate") == pytest.approx(shrunk(1, 4, motion_lg))
    # play action: pass plays only (A 2 passes, 1 PA; B 1 pass, 0 PA)
    pa_lg = 1 / 3
    assert feat(vals, "g3", "A", "front.play_action_rate") == pytest.approx(shrunk(1, 2, pa_lg))
    # blitz: defense vs dropbacks. B faced A's 2 dropbacks (1 blitz), A faced B's 1 (1 blitz)
    bl_lg = 2 / 3
    assert feat(vals, "g3", "B", "front.blitz_rate") == pytest.approx(shrunk(1, 2, bl_lg))
    assert feat(vals, "g3", "A", "front.blitz_rate") == pytest.approx(shrunk(1, 1, bl_lg))
    # box 8+ vs runs: B faced 2 runs (1 with 8+), A faced 3 runs (2 with 8+)
    bx_lg = 3 / 5
    assert feat(vals, "g3", "B", "front.box_8plus_rate") == pytest.approx(shrunk(1, 2, bx_lg))
    assert feat(vals, "g3", "A", "front.box_8plus_rate") == pytest.approx(shrunk(2, 3, bx_lg))
    # g4 (week 3) adds week 2 with decay 0.5 ** (1 / 6) for week 1 and 1 for week 2
    w1 = 0.5 ** (1 / 6)
    got = feat(vals, "g4", "B", "front.motion_rate")
    league = (3 + 1 + 1 * 1) / (8 + 1)  # prior uses the unweighted league rate
    assert got == pytest.approx(((w1 * 1 + 1) + N0 * league) / (w1 * 4 + 1 + N0))


def test_no_leakage(tmp_path):
    base, _ = run(tmp_path / "a", plays())
    extra = [ftn("g3", 2022, 2, "A", "B", "pass", motion=True, pa=True, blitz=5)] * 5
    mut, _ = run(tmp_path / "b", plays(extra))
    for gid in ("g1", "g2", "g3"):
        for t in "AB":
            for n in base["feature"].unique().to_list():
                a, b = feat(base, gid, t, n), feat(mut, gid, t, n)
                assert a == b or a == pytest.approx(b), (gid, t, n)
    assert feat(base, "g4", "A", "front.motion_rate") != feat(mut, "g4", "A", "front.motion_rate")


def test_build_rows_through_store(tmp_path):
    paths = write_plays(tmp_path, make_plays(plays()))
    rows = front.build(paths, games_frame(), BUILD)
    store.validate(rows)
    assert rows.height == 4 * 2 * 4
    assert set(rows["source"]) == {"ftn"} and set(rows["version"]) == {"1"}


@requires_data
def test_real_data_null_share():
    rows = front.build(DATA, store.games_frame(DATA), datetime(2030, 1, 1))
    played = rows.filter(pl.col("season") <= 2025)
    pre = played.filter(pl.col("season") < 2022)
    assert pre["value"].null_count() == pre.height
    post = played.filter(
        (pl.col("season") >= 2022) & ~((pl.col("season") == 2022) & (pl.col("week") == 1))
    )
    assert post["value"].null_count() / post.height < 0.05
    v = post.drop_nulls("value")["value"]
    assert v.is_finite().all() and v.min() >= 0 and v.max() <= 1
