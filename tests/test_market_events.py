from datetime import datetime, timedelta

import polars as pl

from nfl import market_events as me

T = datetime(2026, 11, 2, 12, 0)
GAME = {"home_team": "BAL", "away_team": "JAX", "week": 9, "kickoff_utc": T + timedelta(days=6)}
POINTS = [{"snapshot_ts": T + timedelta(days=d)} for d in (0, 1, 3)]


def report(*rows):
    return pl.DataFrame(
        [{"team": t, "week": 9, "gsis_id": g, "full_name": n, "position": p, "report_status": s}
         for t, g, n, p, s in rows],
        schema={"team": pl.Utf8, "week": pl.Int64, "gsis_id": pl.Utf8, "full_name": pl.Utf8,
                "position": pl.Utf8, "report_status": pl.Utf8},
    )  # fmt: skip


def test_injury_transitions_between_snapshots():
    snaps = [
        (T, report(("BAL", "lj", "Lamar Jackson", "QB", None))),
        (T + timedelta(days=1), report(("BAL", "lj", "Lamar Jackson", "QB", "Questionable"))),
        (T + timedelta(days=2), report(("BAL", "lj", "Lamar Jackson", "QB", "Out"))),
        (T + timedelta(days=3), report(("BAL", "xx", "Someone Else", "WR", None))),
    ]
    got = [(e["was"], e["status"]) for e in me.injury_transitions(snaps)]
    assert got == [(None, "Questionable"), ("Questionable", "Out"), ("Out", None)]


def test_a_week_missing_from_a_snapshot_is_not_a_change():
    snaps = [
        (T, report(("BAL", "lj", "Lamar Jackson", "QB", "Out"))),
        (T + timedelta(days=1), report()),
    ]
    assert me.injury_transitions(snaps) == []


def test_an_event_belongs_to_the_window_it_falls_in_and_no_other():
    inj = [{"team": "BAL", "week": 9, "gsis_id": "lj", "ts": T + timedelta(days=2), "player": "Lamar Jackson",
            "pos": "QB", "status": "Out", "was": "Questionable"}]  # fmt: skip
    qb = [
        {"team": "BAL", "ts": T + timedelta(hours=1), "qb": "Tyler Huntley", "was": "Lamar Jackson"}
    ]
    ev = me.game_events(GAME, POINTS, qb, inj, set(), [], None)
    assert [(e["kind"], e["after"]) for e in ev] == [("qb", 0), ("injury", 1)]
    assert all("because" not in e["text"] for e in ev)


def test_other_teams_other_weeks_and_after_kickoff_are_left_out():
    inj = [
        {"team": "KC", "week": 9, "gsis_id": "a", "ts": T, "player": "A", "pos": "QB", "status": "Out", "was": None},
        {"team": "BAL", "week": 8, "gsis_id": "b", "ts": T, "player": "B", "pos": "QB", "status": "Out", "was": None},
        {"team": "BAL", "week": 9, "gsis_id": "c", "ts": GAME["kickoff_utc"], "player": "C", "pos": "QB",
         "status": "Out", "was": None},
        {"team": "BAL", "week": 9, "gsis_id": "d", "ts": T, "player": "D", "pos": "WR", "status": "Out", "was": None},
    ]  # fmt: skip
    assert me.game_events(GAME, POINTS, [], inj, set(), [], None) == []
    assert len(me.game_events(GAME, POINTS, [], inj, {"d"}, [], None)) == 1  # a starter counts


def test_qb_changes_from_chart_snapshots():
    depth = pl.DataFrame({
        "team": ["BAL"] * 3, "pos_abb": ["QB"] * 3, "pos_rank": [1] * 3,
        "dt": ["2026-11-01T07:00:00Z", "2026-11-02T07:00:00Z", "2026-11-02T17:00:00Z"],
        "player_name": ["Lamar Jackson", "Lamar Jackson", "Tyler Huntley"],
    })  # fmt: skip
    got = me.qb_changes(depth)
    assert got == [
        {
            "team": "BAL",
            "ts": datetime(2026, 11, 2, 17),
            "qb": "Tyler Huntley",
            "was": "Lamar Jackson",
        }
    ]


def test_no_events_without_a_line():
    assert me.game_events(GAME, [], [], [], set(), [], None) == []


def test_last_weeks_game_is_an_event_with_its_score():
    done = pl.DataFrame({
        "home_team": ["BAL", "KC"], "away_team": ["MIA", "DEN"], "home_score": [17, 30], "away_score": [24, 10],
        "kickoff_utc": [T - timedelta(days=1), T - timedelta(days=1)],
    })  # fmt: skip
    ev = me.game_events(GAME, POINTS, [], [], set(), [], None, me.results(done))
    assert [e["text"] for e in ev] == ["Result: BAL lost to MIA 17–24 (vs MIA)"]
    assert ev[0]["kind"] == "game"
