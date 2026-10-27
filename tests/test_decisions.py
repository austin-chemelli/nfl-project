"""Decisions builder: filters, shrinkage, week-1 = prior, alias handling, leakage."""

from datetime import datetime, timedelta

import duckdb
import polars as pl
import pytest

from nfl.config import Paths
from nfl.features import decisions, store
from nfl.tendencies import N0, shrink_decay, weekly_aggregates
from tests.conftest import DATA, requires_data

T0 = datetime(2023, 9, 10, 17, 0)
BUILD = datetime(2024, 9, 1)

# (id, season, week, days after T0, home, away). OAK is the games-table code for plays' LV.
SCHEDULE = [
    ("g1", 2023, 1, 0, "A", "B"),
    ("h1", 2023, 1, 0, "C", "D"),  # same kickoff as g1: must not feed g1's league rate
    ("g2", 2023, 2, 7, "B", "A"),
    ("h2", 2023, 2, 7, "D", "OAK"),
    ("g3", 2024, 1, 365, "A", "B"),
    ("g4", 2024, 2, 372, "B", "A"),
]
PLAYS_CODE = {"OAK": "LV"}

_BOOL = ("is_motion", "is_play_action", "is_rpo", "is_screen_pass", "has_ftn")
_STR = ("game_id", "posteam", "defteam", "play_type", "qb_location")
_FLOAT = ("epa", "success", "pass_oe")


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


def make_plays(rows: list[dict]) -> pl.DataFrame:
    """rows: dicts with game_id, season, week, posteam, defteam (games-table codes) plus any play
    columns; unspecified columns are null (has_ftn False)."""
    cols = {}
    names = {
        "season", "week", "down", "ydstogo", "yardline_100", "pass", "shotgun", "no_huddle",
        "qb_dropback", "yards_gained", "interception", "fumble_lost", "n_blitzers",
        "n_pass_rushers", "n_defense_box", "qtr", "score_differential", "half_seconds_remaining",
        *_BOOL, *_STR, *_FLOAT,
    }  # fmt: skip
    for n in names:
        dtype = (
            pl.Utf8 if n in _STR else pl.Boolean if n in _BOOL else pl.Float64 if n in _FLOAT
            else pl.Int64
        )  # fmt: skip
        vals = [r.get(n, False if n == "has_ftn" else None) for r in rows]
        if n in ("posteam", "defteam"):
            vals = [PLAYS_CODE.get(v, v) for v in vals]
        cols[n] = pl.Series(n, vals, dtype=dtype)
    return pl.DataFrame(cols)


def write_plays(root, plays: pl.DataFrame) -> Paths:
    paths = Paths(root)
    for (season,), part in plays.partition_by("season", as_dict=True).items():
        d = paths.curated_table("plays") / f"season={season}"
        d.mkdir(parents=True, exist_ok=True)
        part.drop("season").write_parquet(d / "p.parquet")
    return paths


def P(gid, season, week, off, deff, **kw):
    return {"game_id": gid, "season": season, "week": week, "posteam": off, "defteam": deff, **kw}


def fourth(gid, season, week, off, deff, play_type, yd=2, yl=50, down=4):
    return P(
        gid, season, week, off, deff, down=down, ydstogo=yd, yardline_100=yl, play_type=play_type
    )


def base_plays(g2_extra=()):
    r = []
    # g1 (2023 wk1): A 4th-down: run (go), punt; excluded: ydstogo 4, yl 34, yl 66, no_play, 3rd down
    r += [
        fourth("g1", 2023, 1, "A", "B", "run", yl=35),
        fourth("g1", 2023, 1, "A", "B", "punt", yl=65),
    ]
    r += [
        fourth("g1", 2023, 1, "A", "B", "run", yd=4),
        fourth("g1", 2023, 1, "A", "B", "run", yl=34),
        fourth("g1", 2023, 1, "A", "B", "pass", yl=66),
        fourth("g1", 2023, 1, "A", "B", "no_play"),
        fourth("g1", 2023, 1, "A", "B", "pass", down=3),
    ]
    r += [fourth("g1", 2023, 1, "B", "A", "field_goal"), fourth("g1", 2023, 1, "B", "A", "punt")]
    r += [fourth("h1", 2023, 1, "C", "D", "pass"), fourth("h1", 2023, 1, "D", "C", "punt")]
    # early-down pass_oe, g1 / A: 10, -4, 6 count; down 3, punt and null pass_oe are excluded
    ed = {"down": 1, "ydstogo": 10, "yardline_100": 50}
    r += [
        P("g1", 2023, 1, "A", "B", **ed, play_type="pass", pass_oe=10.0, yards_gained=20, **{"pass": 1}),
        P("g1", 2023, 1, "A", "B", **{**ed, "down": 2}, play_type="run", pass_oe=-4.0, yards_gained=11, **{"pass": 0}),
        P("g1", 2023, 1, "A", "B", **ed, play_type="pass", pass_oe=6.0, yards_gained=19, **{"pass": 1}),
        P("g1", 2023, 1, "A", "B", **{**ed, "down": 3}, play_type="pass", pass_oe=50.0, yards_gained=12, **{"pass": 1}),
        P("g1", 2023, 1, "A", "B", **ed, play_type="run", pass_oe=None, yards_gained=12, **{"pass": 0}),
        P("g1", 2023, 1, "A", "B", **ed, play_type="punt", pass_oe=99.0, yards_gained=50, **{"pass": 0}),
        P("g1", 2023, 1, "B", "A", **ed, play_type="pass", pass_oe=2.0, yards_gained=5, **{"pass": 1}),
    ]  # fmt: skip
    # turnovers g1: A throws an INT and loses a fumble on a run; B loses a fumble on a pass;
    # a fumble lost on a punt is ignored
    r += [
        P("g1", 2023, 1, "A", "B", play_type="pass", interception=1, fumble_lost=0),
        P("g1", 2023, 1, "A", "B", play_type="run", interception=0, fumble_lost=1),
        P("g1", 2023, 1, "B", "A", play_type="pass", interception=None, fumble_lost=1),
        P("g1", 2023, 1, "B", "A", play_type="punt", interception=0, fumble_lost=1),
    ]
    # g2 (2023 wk2): A and B
    r += [fourth("g2", 2023, 2, "A", "B", "run"), fourth("g2", 2023, 2, "A", "B", "punt")]
    r += [
        P("g2", 2023, 2, "A", "B", **ed, play_type="pass", pass_oe=4.0, yards_gained=3, **{"pass": 1}),
        P("g2", 2023, 2, "B", "A", **ed, play_type="run", pass_oe=-2.0, yards_gained=3, **{"pass": 0}),
    ]  # fmt: skip
    r += list(g2_extra)
    # h2: OAK (plays say LV) goes for it, once
    r += [fourth("h2", 2023, 2, "OAK", "D", "pass")]
    r += [P("h2", 2023, 2, "OAK", "D", **ed, play_type="pass", **{"pass": 1})]
    # 2024
    r += [
        P("g3", 2024, 1, "A", "B", **ed, play_type="pass", pass_oe=1.0, yards_gained=1, **{"pass": 1}),
        P("g3", 2024, 1, "B", "A", **ed, play_type="run", pass_oe=1.0, yards_gained=1, **{"pass": 0}),
        P("g4", 2024, 2, "A", "B", **ed, play_type="pass", pass_oe=9.0, yards_gained=1, **{"pass": 1}),
    ]  # fmt: skip
    return r


def run(tmp_path, rows):
    paths = write_plays(tmp_path, make_plays(rows))
    games = games_frame()
    stats = decisions.load_game_stats(paths, 2023)
    weekly = weekly_aggregates(duckdb.connect(), paths, [2023, 2024], ["early_down"])
    return decisions.compute(games, stats, weekly), weekly


def feat(vals, gid, team, name):
    r = vals.filter(
        (pl.col("game_id") == gid) & (pl.col("team") == team) & (pl.col("feature") == name)
    )
    assert r.height == 1, (gid, team, name)
    return r["value"][0]


def test_fourth_go_rate_oe(tmp_path):
    vals, _ = run(tmp_path, base_plays())
    f = "decisions.fourth_go_rate_oe"
    # week 1: no earlier games -> 0 (same-kickoff game h1 does not count for g1)
    for gid, team in (("g1", "A"), ("g1", "B"), ("h1", "C")):
        assert feat(vals, gid, team, f) == 0.0
    # league before g2 = g1 + h1: go 2 (A run, C pass) of 6 qualifying plays (A 2, B 2, C 1, D 1)
    lg = 2 / 6
    assert feat(vals, "g2", "A", f) == pytest.approx((1 - 2 * lg) / (2 + 10))  # A: 1 go of 2
    assert feat(vals, "g2", "B", f) == pytest.approx((0 - 2 * lg) / (2 + 10))
    # OAK (games code) is matched to the plays' LV: no prior games for it in 2023 -> 0
    assert feat(vals, "h2", "OAK", f) == 0.0
    # new season resets
    assert feat(vals, "g3", "A", f) == 0.0
    # g4: season 2024 has one earlier game with no qualifying 4th downs -> no league data -> 0
    assert feat(vals, "g4", "B", f) == 0.0


def test_alias_team_gets_history(tmp_path):
    rows = base_plays() + [fourth("h3", 2023, 2, "D", "OAK", "punt")]
    vals, _ = run(tmp_path, rows)
    # D played h1 (1 punt) so its h2 value uses h1; OAK's own plays are in h2 only, so check D
    assert feat(vals, "h2", "D", "decisions.fourth_go_rate_oe") == pytest.approx(
        (0 - 1 * (2 / 6)) / (1 + 10)
    )


def test_pass_rate_oe_filters_shrinkage_and_prior(tmp_path):
    vals, _ = run(tmp_path, base_plays())
    f = "decisions.pass_rate_oe"
    assert feat(vals, "g1", "A", f) == 0.0  # 2023: no previous season -> prior 0
    assert feat(vals, "g2", "A", f) == pytest.approx((10 - 4 + 6) / (3 + 150))
    assert feat(vals, "g2", "B", f) == pytest.approx(2.0 / (1 + 150))
    # 2024 week 1: 0.7 * team's 2023 mean + 0.3 * league 2023 mean
    # A 2023: 10 - 4 + 6 + 4 = 16 over 4; B: 2 - 2 = 0 over 2; league 16 / 6
    assert feat(vals, "g3", "A", f) == pytest.approx(0.7 * 16 / 4 + 0.3 * 16 / 6)
    assert feat(vals, "g3", "B", f) == pytest.approx(0.7 * 0 + 0.3 * 16 / 6)
    prior_a = 0.7 * 16 / 4 + 0.3 * 16 / 6
    assert feat(vals, "g4", "A", f) == pytest.approx((1.0 + 150 * prior_a) / (1 + 150))


def test_explosive_rate(tmp_path):
    vals, _ = run(tmp_path, base_plays())
    f = "decisions.explosive_rate"
    assert feat(vals, "g1", "A", f) == pytest.approx(0.09)  # default prior, 2023
    # pass >= 20 and run >= 12 count; the denominator is every pass/run play, nulls included
    s = feat(vals, "g2", "A", f)
    # recompute the expected counts directly from the rows
    rows = [r for r in base_plays() if r["game_id"] == "g1" and r["posteam"] == "A"]
    pr = [r for r in rows if r["play_type"] in ("pass", "run")]
    ex = [
        r
        for r in pr
        if (r["play_type"] == "pass" and (r.get("yards_gained") or 0) >= 20)
        or (r["play_type"] == "run" and (r.get("yards_gained") or 0) >= 12)
    ]
    assert len(ex) == 2
    assert s == pytest.approx((len(ex) + 200 * 0.09) / (len(pr) + 200))


def test_turnover_margin(tmp_path):
    vals, _ = run(tmp_path, base_plays())
    f = "decisions.turnover_margin_pg"
    assert feat(vals, "g1", "A", f) == 0.0
    # g1: A gave 2 (INT + fumble on a run), took 1 (B's fumble on a pass); punt fumble ignored
    assert feat(vals, "g2", "A", f) == pytest.approx(-1 / (1 + 4))
    assert feat(vals, "g2", "B", f) == pytest.approx(1 / (1 + 4))
    # 2024 week 1: season-to-date resets
    assert feat(vals, "g3", "A", f) == 0.0


def test_early_down_pass_rate_matches_tendencies_and_aliases(tmp_path):
    vals, weekly = run(tmp_path, base_plays())
    f = "decisions.early_down_pass_rate"
    for gid, team, season, week in (("g2", "A", 2023, 2), ("g4", "B", 2024, 2)):
        t = shrink_decay(weekly, season, week).filter(
            (pl.col("team") == team) & (pl.col("metric") == "pass_rate")
        )
        assert feat(vals, gid, team, f) == pytest.approx(t["rate"][0])
    # LV in the plays, OAK in games: matched through the alias; no week-1 plays -> league prior
    lg = shrink_decay(weekly, 2023, 2).filter(
        (pl.col("team") == "LV") & (pl.col("metric") == "pass_rate")
    )["rate"][0]
    assert feat(vals, "h2", "OAK", f) == pytest.approx(lg)
    assert N0 == 50.0


def test_no_leakage(tmp_path):
    base, _ = run(tmp_path / "a", base_plays())
    extra = [
        P("g2", 2023, 2, "A", "B", down=1, ydstogo=10, yardline_100=50, play_type="pass",
          pass_oe=80.0, yards_gained=90, interception=1, **{"pass": 1}),
        fourth("g2", 2023, 2, "A", "B", "run"),
        fourth("g2", 2023, 2, "B", "A", "run"),
    ]  # fmt: skip
    mut, _ = run(tmp_path / "b", base_plays(extra))
    names = base["feature"].unique().to_list()
    for gid, teams in (("g1", "AB"), ("g2", "AB"), ("h1", "CD")):
        for t in teams:
            for n in names:
                assert feat(base, gid, t, n) == pytest.approx(feat(mut, gid, t, n)), (gid, t, n)
    # sanity: the next season's week-1 prior does see g2
    assert feat(base, "g3", "A", "decisions.pass_rate_oe") != feat(
        mut, "g3", "A", "decisions.pass_rate_oe"
    )


def test_build_rows_through_store(tmp_path):
    paths = write_plays(tmp_path, make_plays(base_plays()))
    rows = decisions.build(paths, games_frame(), BUILD)
    store.validate(rows)
    assert rows.height == len(SCHEDULE) * 2 * 5
    assert set(rows["source"]) == {"pbp"} and set(rows["version"]) == {"1"}
    assert rows.filter(pl.col("game_id") == "g1")["known_as_of"].n_unique() == 1


@requires_data
def test_real_data():
    games = store.games_frame(DATA)
    rows = decisions.build(DATA, games, datetime(2030, 1, 1))
    v = rows.drop_nulls("value")
    assert v["value"].is_finite().all()
    # null audit: pass_oe coverage on early-down pass/run plays from 2006 on (null before)
    con = duckdb.connect()
    glob = f"{DATA.curated_table('plays').as_posix()}/*/*.parquet"
    cov = con.sql(
        f"select season, avg((pass_oe is not null)::int) c from read_parquet('{glob}', "
        "hive_partitioning=true) where down in (1,2) and play_type in ('pass','run') "
        "and season >= 2006 group by 1"  # nflfastR's xpass model starts in 2006
    ).pl()
    assert cov["c"].min() > 0.95, cov.sort("c").head(3)
    # non-tendency features are never null; the league mean of the 4th-down feature is ~0
    for name in ("pass_rate_oe", "explosive_rate", "fourth_go_rate_oe", "turnover_margin_pg"):
        assert rows.filter(pl.col("feature") == f"decisions.{name}")["value"].null_count() == 0
    go = rows.filter(pl.col("feature") == "decisions.fourth_go_rate_oe")
    by_season = go.group_by("season").agg(pl.col("value").mean().alias("m"))
    assert by_season["m"].abs().max() < 0.03, by_season.sort("m")
