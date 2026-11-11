import json

import polars as pl
import pytest

from nfl import candidate_screen as cs
from nfl import catalog
from nfl.config import Paths
from nfl.sql import runner

from .synth import league, play, write_games, write_participation, write_plays


def games_for(*ids_weeks):
    return [
        {"game_id": g, "season": 2022, "week": w, "home_team": "A", "away_team": "B", "result": 3}
        for g, w in ids_weeks
    ]


def planted():
    """Team A's offense in game g1 (week 1): 4 plays, one an interception, one a lost fumble, one a
    sack; plus a punt-like play with epa null and a kneel (neither pass nor rush)."""
    return [
        play(season=2022, game_id="g1", play_id=1, epa=1.0, success=1.0, wp=0.5, pass_oe=10.0),
        play(season=2022, game_id="g1", play_id=2, epa=-2.0, interception=1.0, wp=0.5, pass_oe=20.0),
        play(season=2022, game_id="g1", play_id=3, epa=-1.0, fumble=1.0, fumble_lost=1.0, rush=1.0,
             **{"pass": 0.0}, qb_dropback=0.0, wp=0.95, down=3.0),
        play(season=2022, game_id="g1", play_id=4, epa=-0.5, sack=1.0, wp=0.5, qtr=4.0, pass_oe=5.0),
        play(season=2022, game_id="g1", play_id=5, epa=None),
        play(season=2022, game_id="g1", play_id=6, epa=0.3, **{"pass": 0.0}, rush=0.0),
        play(season=2022, game_id="g1", play_id=7, epa=0.2, fumble=1.0, rush=1.0, wp=0.5,
             **{"pass": 0.0}, qb_dropback=0.0, posteam="B", defteam="A", success=1.0),
    ]  # fmt: skip


def tw(paths) -> pl.DataFrame:
    runner.build(paths, "team_week")
    return pl.read_parquet(runner.output_path(paths, "team_week"))


def row(df, team, side, week=1):
    return df.filter(
        (pl.col("team") == team) & (pl.col("side") == side) & (pl.col("week") == week)
    ).row(0, named=True)


def test_team_week_sums_for_a_planted_team_week(tmp_path):
    paths = Paths(tmp_path)
    write_plays(paths, planted())
    write_games(paths, games_for(("g1", 1)))
    write_participation(
        paths,
        [{"game_id": "g1", "play_id": 1.0, "was_pressure": True, "time_to_throw": 2.5, "season": 2022},
         {"game_id": "g1", "play_id": 2.0, "was_pressure": False, "time_to_throw": 3.5, "season": 2022}],
    )  # fmt: skip
    df = tw(paths)
    assert df.height == 4  # A off, B def, B off, A def
    a = row(df, "A", "off")
    assert a["plays"] == 4  # null epa and the non-pass non-rush play are out
    assert a["epa_sum"] == pytest.approx(1.0 - 2.0 - 1.0 - 0.5)
    assert a["epa_noto_sum"] == pytest.approx(1.0 - 0.5)
    assert a["success_sum"] == 1
    assert (a["dropbacks"], a["sacks"], a["interceptions"]) == (3, 1, 1)
    assert (a["fumbles"], a["fumbles_lost"], a["takeaways"]) == (1, 1, 2)
    assert a["proe_sum"] == pytest.approx(10.0 + 20.0)  # downs 1-2, wp .2-.8, qtr <= 3, not null
    assert a["proe_n"] == 2
    assert a["neutral_plays"] == 3  # all but the wp 0.95 play
    w = 4 * 0.5 * 0.5
    assert a["wepa_w"] == pytest.approx(3 * w + 4 * 0.95 * 0.05)
    assert a["wepa_sum"] == pytest.approx((1.0 - 2.0 - 0.5) * w + -1.0 * 4 * 0.95 * 0.05)
    assert (a["pressures"], a["ttt_sum"], a["ttt_n"]) == (1, 6.0, 2)
    # the defense row is what B's defense did to A: same plays, grouped by defteam
    d = row(df, "B", "def")
    assert (d["plays"], d["takeaways"], d["epa_sum"]) == (4, 2, a["epa_sum"])
    assert row(df, "B", "off")["fumbles"] == 1 and row(df, "B", "off")["fumbles_lost"] == 0
    # no participation row: pressure stays null
    assert row(df, "B", "off")["pressures"] is None


def test_idempotent_build_does_not_rewrite(tmp_path):
    paths = Paths(tmp_path)
    write_plays(paths, planted())
    write_games(paths, games_for(("g1", 1)))
    write_participation(paths, [{"game_id": "g0", "play_id": 1.0, "was_pressure": None,
                                 "time_to_throw": None, "season": 2022}])  # fmt: skip
    (r1,) = runner.build(paths, "team_week")
    target = runner.output_path(paths, "team_week")
    assert r1.status == "written" and r1.rows == 4
    meta = json.loads(runner.sidecar_path(paths, "team_week").read_text())
    assert meta == {"sql_sha256": runner.sql_hash("team_week"), "rows": 4}
    before = target.stat().st_mtime_ns
    (r2,) = runner.build(paths, "team_week")
    assert r2.status == "unchanged" and target.stat().st_mtime_ns == before
    # different input -> rewritten
    write_plays(paths, planted() + [play(season=2022, game_id="g1", play_id=9, epa=0.4)])
    (r3,) = runner.build(paths, "team_week")
    assert r3.status == "written" and target.stat().st_mtime_ns != before
    # an edited SQL file with the same output updates the sidecar only
    runner.sidecar_path(paths, "team_week").write_text('{"sql_sha256": "old", "rows": 4}')
    (r4,) = runner.build(paths, "team_week")
    assert r4.status == "sql changed, output unchanged"
    assert json.loads(runner.sidecar_path(paths, "team_week").read_text())["sql_sha256"] == (
        runner.sql_hash("team_week")
    )


def test_unknown_model_is_an_error(tmp_path):
    with pytest.raises(ValueError):
        runner.build(Paths(tmp_path), "nope")


def test_the_derived_table_is_a_catalog_view(tmp_path):
    paths = Paths(tmp_path)
    write_plays(paths, planted())
    write_games(paths, games_for(("g1", 1)))
    write_participation(paths, [{"game_id": "g0", "play_id": 1.0, "was_pressure": None,
                                 "time_to_throw": None, "season": 2022}])  # fmt: skip
    assert "team_week" in catalog.missing(paths)
    runner.build(paths, "team_week")
    assert "team_week" not in catalog.missing(paths)
    con = catalog.connect(paths)
    assert con.sql("select sum(plays) from team_week where side = 'off'").fetchall()[0][0] == 5


def test_a_week_w_play_changes_week_w_but_never_the_as_of_values_for_week_w(tmp_path):
    """Leakage (ADR 0026): team_week rows are per week; the as-of frame sums only earlier weeks."""

    def build(root, extra):
        paths = Paths(root)
        write_plays(
            paths,
            [play(season=2022, game_id=g, play_id=1, epa=0.1 * w, week=w) for g, w in G] + extra,
        )
        write_games(paths, games_for(*G))
        write_participation(paths, [{"game_id": "x", "play_id": 1.0, "was_pressure": None,
                                     "time_to_throw": None, "season": 2022}])  # fmt: skip
        runner.build(paths, "team_week")
        t = pl.read_parquet(runner.output_path(paths, "team_week"))
        games = catalog.connect(paths).sql("select * from games").pl()
        return t, cs.asof_frame(cs.team_games(t, games))

    G = [("g1", 1), ("g2", 2), ("g3", 3)]
    planted_play = [play(season=2022, game_id="g2", play_id=99, epa=50.0, week=2, interception=1.0)]
    t0, a0 = build(tmp_path / "a", [])
    t1, a1 = build(tmp_path / "b", planted_play)
    # the week-2 team_week row moved...
    assert row(t0, "A", "off", 2)["epa_sum"] != row(t1, "A", "off", 2)["epa_sum"]
    # ...the as-of values for week 2 (and every earlier week) did not...
    key = ["game_id", "team"]
    for g in ("g1", "g2"):
        x = a0.filter(pl.col("game_id") == g).sort(key)
        y = a1.filter(pl.col("game_id") == g).sort(key)
        assert x.equals(y), g
    # ...and week 3's did, so the test would catch a swap of < for <=.
    x = a0.filter(pl.col("game_id") == "g3").sort(key)
    y = a1.filter(pl.col("game_id") == "g3").sort(key)
    assert not x.equals(y)


def test_league_fixture_builds(tmp_path):
    paths = Paths(tmp_path)
    plays, _ = league(paths)
    assert tw_rows(paths) == 2 * 4 * 8 * 8  # side x seasons x weeks x teams
    assert len(plays) == 4 * 8 * 4 * 20


def tw_rows(paths) -> int:
    write_participation(paths, [{"game_id": "x", "play_id": 1.0, "was_pressure": None,
                                 "time_to_throw": None, "season": 2020}])  # fmt: skip
    (r,) = runner.build(paths, "team_week")
    return r.rows
