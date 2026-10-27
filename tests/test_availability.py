"""Availability builder tests: synthetic frames for both depth-chart formats, plus real-data guards."""

from datetime import datetime, timedelta

import duckdb
import polars as pl

from nfl.features import availability, store
from tests.conftest import DATA, requires_data

BUILD = datetime(2030, 1, 1)


def _games(rows):
    """rows: (game_id, season, week, kickoff, home, away)."""
    return pl.DataFrame(
        [
            {
                "game_id": g,
                "season": s,
                "week": w,
                "kickoff_utc": k,
                "home_team": h,
                "away_team": a,
            }
            for g, s, w, k, h, a in rows
        ]
    )


def _weekly(season, week, club, players):
    """players: (position, depth_position, gsis_id[, depth_team]) in listing order."""
    return [
        {
            "season": season,
            "week": week,
            "club_code": club,
            "depth_team": p[3] if len(p) > 3 else "1",
            "position": p[0],
            "depth_position": p[1],
            "gsis_id": p[2],
        }
        for p in players
    ]


def _snap(team, dt, players):
    """players: (pos_abb, pos_slot, gsis_id[, pos_rank])."""
    return [
        {
            "season": 2025,
            "team": team,
            "dt": dt,
            "pos_abb": p[0],
            "pos_slot": p[1],
            "gsis_id": p[2],
            "pos_rank": p[3] if len(p) > 3 else 1,
        }
        for p in players
    ]


def _inj(season, week, team, rows):
    return [
        {"season": season, "week": week, "team": team, "gsis_id": g, "report_status": s}
        for g, s in rows
    ]


def _plays(game_id, posteam, passers):
    """passers: {gsis_id: dropbacks}."""
    return [
        {"game_id": game_id, "posteam": posteam, "passer_player_id": p}
        for p, n in passers.items()
        for _ in range(n)
    ]


def _frame(rows, schema=None):
    return pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)


INJ_SCHEMA = {
    "season": pl.Int64,
    "week": pl.Int64,
    "team": pl.Utf8,
    "gsis_id": pl.Utf8,
    "report_status": pl.Utf8,
}
PLAY_SCHEMA = {"game_id": pl.Utf8, "posteam": pl.Utf8, "passer_player_id": pl.Utf8}


def run(games, inj, depth, plays, build=BUILD):
    df = availability.compute(
        games,
        _frame(inj, INJ_SCHEMA),
        pl.concat([pl.DataFrame(d) for d in depth], how="diagonal")
        if isinstance(depth, list)
        else depth,
        _frame(plays, PLAY_SCHEMA),
        build,
    )
    return {
        (r["game_id"], r["team"], r["feature"].split(".")[1]): r["value"]
        for r in df.iter_rows(named=True)
    }


T0 = datetime(2018, 9, 9, 17, 0)

STARTERS_W2 = [
    ("QB", "QB", "q1"),
    ("T", "LT", "t1"),
    ("G", "LG", "g1"),
    ("C", "C", "c0"),
    ("WR", "WR", "w1"),
    ("WR", "WR", "w2"),
    ("CB", "LCB", "cb1"),
    ("CB", "RCB", "cb2"),
    ("CB", "NB", "nb1"),
    ("DT", "DT", "dt1"),
    ("K", "K", "k1"),
    ("RB", "KR", "rb1"),  # also a kick returner: excluded as returner, but listed twice below
    ("RB", "RB", "rb1"),
    ("QB", "QB", "q2", "2"),  # depth 2: ignored
]


def test_weekly_status_weights_and_qb_out():
    games = _games(
        [
            ("g1", 2018, 1, T0, "AAA", "BBB"),
            ("g2", 2018, 2, T0 + timedelta(days=7), "AAA", "BBB"),
            ("g3", 2018, 3, T0 + timedelta(days=14), "AAA", "BBB"),
        ]
    )
    depth = [
        _weekly(2018, 1, "AAA", [("QB", "QB", "q1")]),
        _weekly(2018, 2, "AAA", STARTERS_W2),
        _weekly(2018, 3, "AAA", [("QB", "QB", "q2")]),
    ]
    inj = _inj(
        2018,
        2,
        "AAA",
        [
            ("q1", "Out"),  # QB 5
            ("t1", "Questionable"),  # T 2 * 0.5 = 1
            ("g1", "Doubtful"),  # G 1 ; counts as OL out
            ("w1", "Doubtful"),  # top WR 2
            ("w2", "Out"),  # second WR 1
            ("cb1", "Out"),  # top CB 2
            ("cb2", "Questionable"),  # second CB 1 * 0.5
            ("nb1", "Probable"),  # 0
            ("k1", "Out"),  # kicker: not a starter for us
            ("zz", "Out"),  # not on the depth chart
            ("c0", None),  # practice-only row: report row, no status
            ("dt1", "Out"),  # DT 1
        ],
    )
    plays = _plays("g1", "AAA", {"q1": 30, "q2": 2}) + _plays("g2", "AAA", {"q1": 4, "q2": 20})
    v = run(games, inj, depth, plays)
    assert v[("g2", "AAA", "qb1_out")] == 1.0
    # out: q1, g1, w1, w2, cb1, dt1 = 6 (k1 excluded, zz not a starter)
    assert v[("g2", "AAA", "starters_out")] == 6.0
    assert v[("g2", "AAA", "ol_starters_out")] == 1.0
    assert v[("g2", "AAA", "injury_impact")] == 5 + 1 + 1 + 2 + 1 + 2 + 0.5 + 1
    # report_count: Out/Doubtful/Questionable only (Probable was abolished in 2016)
    assert v[("g2", "AAA", "report_count")] == 10.0
    # q1 was the primary passer of g1 -> no change; g3 starts q2, g2's primary passer was q2
    assert v[("g2", "AAA", "qb_change")] == 0.0
    assert v[("g3", "AAA", "qb_change")] == 0.0  # q2 threw most in g2
    # first game: no previous passer; no injury report for BBB -> nulls, no chart either
    assert v[("g1", "AAA", "qb_change")] is None
    assert v[("g2", "BBB", "qb1_out")] is None
    assert v[("g2", "BBB", "report_count")] is None


def test_qb_change_and_missing_report():
    games = _games(
        [
            ("g1", 2018, 1, T0, "AAA", "BBB"),
            ("g2", 2018, 2, T0 + timedelta(days=7), "AAA", "BBB"),
        ]
    )
    depth = [
        _weekly(2018, 1, "AAA", [("QB", "QB", "q1")]),
        _weekly(2018, 2, "AAA", [("QB", "QB", "q2"), ("QB", "QB", "q1", "2")]),
    ]
    plays = _plays("g1", "AAA", {"q1": 25})
    inj = _inj(2018, 2, "AAA", [("q2", "Questionable")])
    v = run(games, inj, depth, plays)
    assert v[("g2", "AAA", "qb_change")] == 1.0
    assert v[("g2", "AAA", "qb1_out")] == 0.0  # Questionable is not out
    assert v[("g2", "AAA", "injury_impact")] == 2.5
    # chart present for wk1 but no report that week: injury features null, qb_change still null
    # only because there is no earlier game
    assert v[("g1", "AAA", "qb1_out")] is None
    assert v[("g1", "AAA", "injury_impact")] is None


def test_pre_2009_is_null():
    games = _games([("g0", 2005, 1, datetime(2005, 9, 11, 17, 0), "AAA", "BBB")])
    v = run(games, [], [pl.DataFrame(_weekly(2018, 1, "AAA", [("QB", "QB", "q1")]))], [])
    assert {k[2] for k in v} == {f.split(".")[1] for f in availability.FEATURES}
    assert all(x is None for x in v.values())


def test_relocation_codes():
    games = _games(
        [
            ("g6", 2018, 6, T0, "SD", "BBB"),
            ("g8", 2019, 1, datetime(2019, 9, 8, 17, 0), "LAC", "BBB"),
        ]
    )
    depth = [
        _weekly(2018, 6, "SD", [("QB", "QB", "p1"), ("T", "LT", "t1")]),
        _weekly(2019, 1, "LAC", [("QB", "QB", "p2")]),
    ]
    inj = _inj(2018, 6, "LAC", [("p1", "Out"), ("t1", "Out")])  # report under the new code
    plays = _plays("g6", "LAC", {"p1": 10})  # pbp prints the current code for old seasons
    inj += _inj(2019, 1, "LAC", [("p2", "Questionable")])
    v = run(games, inj, depth, plays)
    assert v[("g6", "SD", "qb1_out")] == 1.0
    assert v[("g6", "SD", "starters_out")] == 2.0
    assert v[("g8", "LAC", "qb_change")] == 1.0  # p2 vs p1 across SD -> LAC
    assert v[("g8", "LAC", "qb1_out")] == 0.0


KICK = datetime(2025, 9, 14, 17, 0)


def test_timestamped_charts_ignore_later_snapshots():
    games = _games([("g1", 2025, 2, KICK, "AAA", "BBB")])
    snaps = (
        _snap("AAA", "2025-09-09T10:00:00Z", [("QB", 1, "early"), ("LT", 2, "t1")])
        # 1h before kickoff: after the kickoff-2h stamp, so not usable
        + _snap("AAA", "2025-09-14T16:00:00Z", [("QB", 1, "late"), ("LT", 2, "t1")])
        # after kickoff
        + _snap("AAA", "2025-09-15T10:00:00Z", [("QB", 1, "after"), ("LT", 2, "t1")])
        + _snap("AAA", "2025-09-09T10:00:00Z", [("QB", 3, "backup", 2)])  # rank 2: ignored
    )
    inj = _inj(
        2025,
        2,
        "AAA",
        [("early", "Out"), ("late", "Questionable"), ("after", "Out"), ("t1", "Out")],
    )
    v = run(games, inj, [snaps], _plays("p", "AAA", {}))
    assert v[("g1", "AAA", "qb1_out")] == 1.0  # the snapshot used has 'early' as QB1
    assert v[("g1", "AAA", "starters_out")] == 2.0
    # now only the post-kickoff snapshot exists for this team: nothing usable
    only_late = _snap("AAA", "2025-09-15T10:00:00Z", [("QB", 1, "after")])
    v = run(games, inj, [only_late], [])
    assert v[("g1", "AAA", "qb1_out")] is None
    assert v[("g1", "AAA", "starters_out")] is None
    assert v[("g1", "AAA", "report_count")] == 4.0  # the report itself does not need a chart


def test_upcoming_game_uses_snapshots_up_to_build_time():
    build = datetime(2025, 9, 11, 12, 0)
    snaps = _snap("AAA", "2025-09-10T10:00:00Z", [("QB", 1, "x")]) + _snap(
        "AAA", "2025-09-12T10:00:00Z", [("QB", 1, "y")]
    )
    prev_games = _games(
        [
            ("g0", 2025, 1, datetime(2025, 9, 7, 17, 0), "AAA", "CCC"),
            ("g1", 2025, 2, KICK, "AAA", "BBB"),
        ]
    )
    inj = _inj(2025, 2, "AAA", [("x", "Out"), ("y", "Out")])
    plays = _plays("g0", "AAA", {"x": 20})
    v = run(prev_games, inj, [snaps], plays, build)
    assert v[("g1", "AAA", "qb1_out")] == 1.0
    assert v[("g1", "AAA", "qb_change")] == 0.0  # x started g0; y (after build) is not seen


def test_store_rows_and_stamp():
    games = _games([("g1", 2025, 2, KICK, "AAA", "BBB")])
    df = availability.compute(
        games,
        _frame(_inj(2025, 2, "AAA", [("x", "Out")]), INJ_SCHEMA),
        pl.DataFrame(_snap("AAA", "2025-09-09T10:00:00Z", [("QB", 1, "x")])),
        _frame([], PLAY_SCHEMA),
        BUILD,
    )
    rows = store.from_team_values(
        df, games, source=availability.SOURCE, version=availability.VERSION, build_ts=BUILD
    )
    assert set(rows["feature"]) == set(availability.FEATURES)
    assert set(rows["side"]) == {"home", "away"}
    assert (rows["known_as_of"] == KICK - timedelta(hours=2)).all()


@requires_data
def test_real_data_coverage_and_known_qb_out():
    games = store.games_frame(DATA)
    rows = availability.build(DATA, games, BUILD)
    kinds = games.select("game_id", "game_type")
    r = rows.join(kinds, on="game_id")

    pre = r.filter(pl.col("season") < 2009)
    assert pre.height and pre["value"].null_count() == pre.height

    reg = r.filter(
        pl.col("season").is_between(2010, 2024)
        & (pl.col("game_type") == "REG")
        & (pl.col("feature") != "availability.qb_change")
    )
    null_share = reg["value"].null_count() / reg.height
    assert null_share < 0.05, null_share

    # a 2023 team-week whose depth-chart QB1 was reported Out (read straight from curated data)
    con = duckdb.connect()
    d = DATA.curated_table("depth_charts").as_posix() + "/season=2023/*.parquet"
    i = DATA.curated_table("injuries").as_posix() + "/season=2023/*.parquet"
    hit = con.sql(
        f"select d.week, d.club_code from read_parquet('{d}') d "
        f"join read_parquet('{i}') i on i.gsis_id = d.gsis_id and i.week = d.week "
        "and i.report_status = 'Out' "
        "where d.depth_team = '1' and d.position = 'QB' and d.game_type = 'REG' "
        "order by d.week, d.club_code limit 1"
    ).fetchall()
    assert hit, "expected at least one 2023 QB1 Out team-week"
    week, club = hit[0]
    g = games.filter(
        (pl.col("season") == 2023)
        & (pl.col("week") == week)
        & ((pl.col("home_team") == club) | (pl.col("away_team") == club))
    ).row(0, named=True)
    side = "home" if g["home_team"] == club else "away"
    got = rows.filter(
        (pl.col("game_id") == g["game_id"])
        & (pl.col("side") == side)
        & (pl.col("feature") == "availability.qb1_out")
    )["value"].to_list()
    assert got == [1.0]
    assert (
        rows.filter((pl.col("season") == 2023) & (pl.col("feature") == "availability.qb1_out"))[
            "value"
        ].sum()
        > 5
    )
