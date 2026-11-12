"""Formation-map lineups (ADR 0027, M24.5): starters from the chart before the cutoff, values, and a
status only for a listed player."""

from datetime import datetime

import polars as pl

from nfl.players import lineup as L

NOW = datetime(2026, 11, 12, 12, 0)
OLD, NEW, LATE = "2026-11-03T15:00:00Z", "2026-11-10T15:00:00Z", "2026-11-12T13:00:00Z"
RATES = {
    ("Questionable", "WR"): (0.73, 1644),
    ("Out", "WR"): (0.000948, 2100),
    ("Out", "all"): (0.00013, 7673),
}


def _chart(dt, rows):
    """(pos_grp, pos_abb, slot, rank, gsis, name)."""
    return [
        {"team": "HHH", "dt": dt, "pos_grp": g, "pos_abb": a, "pos_slot": s, "pos_rank": r,
         "gsis_id": i, "player_name": n} for g, a, s, r, i, n in rows
    ]  # fmt: skip


O, D = "3WR 1TE", "Base 3-4 D"
DEPTH = pl.DataFrame(
    _chart(OLD, [(O, "QB", 9, 1, "oldqb", "Old QB")])
    + _chart(NEW, [
        (O, "QB", 9, 1, "qb", "Q One"), (O, "QB", 9, 2, "qb2", "Q Two"),
        (O, "WR", 1, 1, "w1", "W One"), (O, "WR", 2, 2, "w2", "W Two"), (O, "WR", 8, 3, "w3", "W Three"),
        (O, "WR", 1, 4, "w4", "W Four"), (O, "FB", 3, 1, "fb", "Full Back"),
        (D, "NT", 4, 1, "nt", "Nose"), (D, "LCB", 8, 1, "cb", "Corner"), (D, "NB", 12, 1, "nb", "Nickel"),
        (D, "FS", 15, 1, None, None), (D, "FS", 15, 2, "fs2", "Backup Safety"),
        (D, "RCB", 9, 1, "traded", "New Arrival"),
        ("Special Teams", "PK", 1, 1, "k", "Kicker"),
    ])
    + _chart(LATE, [(O, "QB", 9, 1, "future", "Future QB")])
)  # fmt: skip
VALUES = pl.DataFrame([
    {"gsis_id": "qb", "team": "HHH", "grp": "QB", "value_pts": 3.0},
    {"gsis_id": "w1", "team": "HHH", "grp": "WR", "value_pts": 1.0},
    {"gsis_id": "cb", "team": "HHH", "grp": "CB", "value_pts": 0.5},
    {"gsis_id": "traded", "team": "OLD", "grp": "CB", "value_pts": 0.7},  # last game for his old team
    {"gsis_id": "w3", "team": "HHH", "grp": "WR", "value_pts": 0.4},
])  # fmt: skip
INJ = [
    {"team": "HHH", "week": 11, "gsis_id": "w1", "pos": "WR", "status": "Questionable"},
    {"team": "HHH", "week": 11, "gsis_id": "cb", "pos": "CB", "status": "Out"},
    {"team": "HHH", "week": 10, "gsis_id": "qb", "pos": "QB", "status": "Out"},  # last week
    {"team": "HHH", "week": 11, "gsis_id": "w2", "pos": "WR", "status": None},  # practice only
    {"team": "HHH", "week": 11, "gsis_id": "w3", "pos": "WR", "status": "Out"},
]


def test_the_latest_chart_before_the_cutoff_one_starter_per_spot():
    s = L.starters(pl.DataFrame(DEPTH), "HHH", NOW)
    assert s["player"].to_list().count("Q One") == 1 and "Future QB" not in s["player"].to_list()
    assert set(s["slot"]) == {"QB", "WR1", "WR2", "WR3", "NT", "LCB", "RCB"}  # no FB, NB or kicker
    # the free safety's starter has no id or name: the spot stays empty, his backup isn't promoted
    assert s.filter(pl.col("slot") == "WR3")["player"][0] == "W Three"


def test_values_and_a_status_only_for_a_listed_player_this_week():
    side = L.side(DEPTH, "HHH", 11, NOW, VALUES, INJ, RATES)
    off = {r["slot"]: r for r in side["offense"]}
    assert [r["slot"] for r in side["offense"]] == ["WR1", "WR2", "WR3", "QB"]
    assert off["QB"]["status"] is None and off["QB"]["value_pts"] == 3.0  # last week's Out is gone
    assert (off["WR1"]["status"], off["WR1"]["p_play"], off["WR1"]["at_risk"]) == ("Questionable", 0.73, 0.27)  # fmt: skip
    assert off["WR2"]["status"] is None and off["WR2"]["value_pts"] is None
    dfn = {r["slot"]: r for r in side["defense"]}
    assert dfn["LCB"]["at_risk"] == 0.5 and dfn["NT"]["grp"] is None  # nose tackles carry no value
    assert dfn["RCB"]["value_pts"] == 0.7  # traded since his last game: still valued
    assert (off["WR3"]["p_play"], off["WR3"]["at_risk"]) == (
        0.0,
        0.4,
    )  # Out never plays, as in claims
    assert side["reported"] and side["chart_ts"] == "2026-11-10T15:00:00Z"
    assert (side["offense_formation"], side["defense_formation"]) == (O, D)


def test_before_any_game_status_the_side_is_not_reported():
    practice_only = [i for i in INJ if i["status"] is None]
    assert not L.side(DEPTH, "HHH", 11, NOW, VALUES, practice_only, RATES)["reported"]


def test_chart_times_are_utc():
    assert (
        L._ts("2026-11-10T10:00:00-05:00")
        == L._ts("2026-11-10T15:00:00Z")
        == L._ts("2026-11-10T15:00:00")
    )


def test_only_games_not_yet_kicked_off_and_none_without_a_chart():
    games = pl.DataFrame([
        {"game_id": "g1", "week": 11, "home_team": "HHH", "away_team": "AAA", "kickoff_utc": datetime(2026, 11, 15)},
        {"game_id": "g0", "week": 10, "home_team": "HHH", "away_team": "AAA", "kickoff_utc": datetime(2026, 11, 8)},
    ])  # fmt: skip
    out = L.lineups(games, DEPTH, VALUES, INJ, RATES, NOW)
    assert list(out) == ["g1"] and out["g1"]["away"] is None
