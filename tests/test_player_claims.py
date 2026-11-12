"""Scored impact claims (ADR 0027, M24.4): who gets a claim, append-only, graded once, never in a lock."""

import inspect
from datetime import datetime, timedelta

import polars as pl

from nfl import lock
from nfl.config import Paths
from nfl.players import claims as C

KICK = datetime(2026, 11, 15, 18, 0)
T1 = datetime(2026, 11, 12, 22, 0)  # Thursday's pass: Questionable
T2 = datetime(2026, 11, 14, 22, 0)  # Saturday's pass: Out
GAME = pl.DataFrame([{"game_id": "2026_11_AAA_HHH", "season": 2026, "week": 11, "kickoff_utc": KICK,
                      "home_team": "HHH", "away_team": "AAA"}])  # fmt: skip
RATES = {("Questionable", "WR"): (0.73, 1644), ("Questionable", "all"): (0.70, 11706),
         ("Doubtful", "all"): (0.01, 1265), ("Out", "all"): (0.0, 7673)}  # fmt: skip


def _inj(rows):
    """(team, gsis, name, position, status)."""
    return pl.DataFrame(
        [{"team": t, "week": 11, "gsis_id": g, "full_name": n, "position": p, "report_status": s}
         for t, g, n, p, s in rows]
    )  # fmt: skip


def _values(rows):
    """(gsis, team, grp, role, value)."""
    return pl.DataFrame(
        [{"season": 2026, "week": 11, "gsis_id": g, "player": g, "team": t, "grp": grp, "role": r,
          "value_pts": v} for g, t, grp, r, v in rows]
    )  # fmt: skip


VALUES = _values([
    ("h1", "HHH", "WR", 0.9, 1.2), ("h2", "HHH", "CB", 0.8, 0.6), ("h3", "HHH", "OL", 0.9, 0.3),
    ("h4", "HHH", "TE", 0.9, 0.25), ("h5", "HHH", "WR", 0.2, 1.0), ("a1", "AAA", "S", 0.9, 0.05),
])  # fmt: skip


def _claims(inj, ts=T1, values=VALUES):
    return C.make(GAME, inj, ts, values, RATES, ts + timedelta(minutes=1))


def test_top_three_listed_starters_by_value_with_their_play_rate():
    c = _claims(_inj([
        ("HHH", "h1", "Hal One", "WR", "Questionable"), ("HHH", "h2", "Hal Two", "CB", "Out"),
        ("HHH", "h3", "Hal Three", "T", "Doubtful"), ("HHH", "h4", "Hal Four", "TE", "Questionable"),
    ]))  # fmt: skip
    assert c["gsis_id"].to_list() == ["h1", "h2", "h3"]
    h1 = c.row(0, named=True)
    assert (h1["p_play"], h1["p_play_n"], h1["rank"], h1["side"]) == (0.73, 1644, 1, "home")
    assert h1["at_risk"] == round(1.2 * 0.27, 2)
    assert h1["sentence"] == ("Hal One is worth about 1.2 points to HHH. Questionable: wide receivers "
                              "listed Questionable have played 73% of the time.")  # fmt: skip
    h2 = c.row(1, named=True)
    assert (h2["p_play"], h2["at_risk"], h2["sentence"]) == (0.0, 0.6, "Hal Two is worth about 0.6 points to HHH. Out.")  # fmt: skip
    assert c.row(2, named=True)["p_play"] == 0.01  # no OL Doubtful rate: the status's overall rate


def test_a_game_with_no_listed_starter_writes_no_claim():
    c = _claims(_inj([
        ("HHH", "h5", "Backup", "WR", "Out"),  # role 0.2: not a starter
        ("AAA", "a1", "Tiny", "S", "Questionable"),  # value under MIN_VALUE
        ("HHH", "h1", "Healthy", "WR", None),  # practice report only, no game status
        ("HHH", "zz", "Unvalued", "LB", "Out"),  # no value row (not a v1 group)
    ]))  # fmt: skip
    assert c.is_empty()


def test_append_is_append_only_and_a_snapshot_is_looked_at_once(tmp_path):
    paths = Paths(tmp_path)
    q = _inj([("HHH", "h1", "Hal One", "WR", "Questionable")])
    assert C.append(paths, _claims(q), GAME, T1, T1) == 1
    # same snapshot, values moved in between: nothing added, no fourth rank
    moved = _values([("h1", "HHH", "WR", 0.9, 1.2), ("h2", "HHH", "CB", 0.8, 0.6)])
    again = _claims(_inj([("HHH", "h1", "Hal One", "WR", "Questionable"), ("HHH", "h2", "H2", "CB", "Out")]), values=moved)  # fmt: skip
    assert C.append(paths, again, GAME, T1, T1 + timedelta(hours=1)) == 0
    later = _claims(_inj([("HHH", "h1", "Hal One", "WR", "Out")]), ts=T2)
    assert C.append(paths, later, GAME, T2, T2) == 1
    stored = C.load(paths)
    assert stored.height == 2 and stored.row(0, named=True)["status"] == "Questionable"
    assert C.load_passes(paths).height == 2


def test_a_snapshot_with_nobody_listed_replaces_older_claims_on_the_pages(tmp_path):
    paths = Paths(tmp_path)
    C.append(paths, _claims(_inj([("HHH", "h1", "Hal One", "WR", "Questionable")])), GAME, T1, T1)
    C.append(paths, _claims(_inj([("HHH", "zz", "Nobody", "LB", None)]), ts=T2), GAME, T2, T2)
    claims, passes = C.load(paths), C.load_passes(paths)
    assert C.key_players(claims, passes)["2026_11_AAA_HHH"] == {"home": [], "away": []}
    a = C.availability(VALUES, claims, passes, "HHH")
    assert a["reported"] and a["value_at_risk"] == 0.0 and a["players"][0]["status"] is None


def test_availability_before_any_report_is_unknown_not_zero():
    a = C.availability(VALUES, pl.DataFrame(schema=C.SCHEMA), pl.DataFrame(schema=C.PASS_SCHEMA), "HHH")  # fmt: skip
    assert (a["reported"], a["value_at_risk"]) == (False, None)


def _pt(ts, spread):
    return {"snapshot_ts": ts, "spread_home": spread}


POINTS = {
    "2026_11_AAA_HHH": [_pt(T1 + timedelta(minutes=2), 3.0), _pt(T2 + timedelta(minutes=2), 2.0)]
}
OUT = [
    {"team": "HHH", "week": 11, "gsis_id": "h1", "ts": T2, "status": "Out", "was": "Questionable"}
]
PASSES = pl.DataFrame([
    {"pass_ts": t, "injury_ts": t, "season": 2026, "week": 11, "game_id": "2026_11_AAA_HHH",
     "home_team": "HHH", "away_team": "AAA"} for t in (T1, T2)
], schema=C.PASS_SCHEMA)  # fmt: skip


def _both():
    return pl.concat([
        _claims(_inj([("HHH", "h1", "Hal One", "WR", "Questionable")])),
        _claims(_inj([("HHH", "h1", "Hal One", "WR", "Out")]), ts=T2),
    ])  # fmt: skip


def test_a_change_to_out_grades_the_last_claim_before_it_against_the_line_move():
    g = C.grade(_both(), OUT, POINTS, set(), T2)
    assert g.height == 1
    r = g.row(0, named=True)
    assert r["claim_id"].endswith(f"{T1:%Y%m%dT%H%M%S}")
    assert r["expected"] == round(1.2 * 0.73, 2)
    assert r["moved"] == 1.0  # home favored by 3, then by 2: one point toward the away team
    assert (r["line_before"], r["line_after"], r["hours"]) == (3.0, 2.0, 48.0)


def test_an_away_player_moving_the_line_reads_toward_the_home_team():
    away = C.make(GAME, _inj([("AAA", "a9", "Al", "WR", "Questionable")]), T1,
                  _values([("a9", "AAA", "WR", 0.9, 1.0)]), RATES, T1)  # fmt: skip
    out = [{**OUT[0], "team": "AAA", "gsis_id": "a9"}]
    pts = {"2026_11_AAA_HHH": [_pt(T1, 3.0), _pt(T2, 4.0)]}
    assert C.grade(away, out, pts, set(), T2)["moved"].to_list() == [1.0]


def test_a_graded_claim_is_never_regraded():
    first = C.grade(_both(), OUT, POINTS, set(), T2)
    later_pts = {
        "2026_11_AAA_HHH": POINTS["2026_11_AAA_HHH"] + [_pt(T2 + timedelta(hours=5), -1.0)]
    }
    again = C.grade(_both(), OUT, later_pts, set(first["claim_id"]), T2 + timedelta(hours=6))
    assert again.is_empty()


def test_no_grade_without_a_line_after_the_change_or_when_it_comes_after_kickoff():
    one_side = {"2026_11_AAA_HHH": POINTS["2026_11_AAA_HHH"][:1]}
    assert C.grade(_both(), OUT, one_side, set(), T2).is_empty()
    late = [{**OUT[0], "ts": KICK + timedelta(hours=1)}]
    assert C.grade(_both(), late, POINTS, set(), KICK + timedelta(hours=2)).is_empty()


def test_the_before_line_is_the_claims_own_not_one_taken_after_the_news():
    # the news breaks; a lock-time snapshot prices it before our next ingest sees Out
    pts = {"2026_11_AAA_HHH": [_pt(T1 + timedelta(minutes=2), 3.0), _pt(T2 - timedelta(hours=3), 2.1),
                               _pt(T2 + timedelta(minutes=2), 2.0)]}  # fmt: skip
    r = C.grade(_both(), OUT, pts, set(), T2).row(0, named=True)
    assert (r["line_before"], r["moved"]) == (3.0, 1.0)


def test_no_grade_when_his_status_changed_between_the_claim_and_out():
    cleared_then_out = [{**OUT[0], "was": None}]  # Questionable, tag removed, then Out
    assert C.grade(_both(), cleared_then_out, POINTS, set(), T2).is_empty()


def test_key_players_come_from_the_latest_snapshot_and_the_record_from_grades():
    both = _both()
    kp = C.key_players(both, PASSES)["2026_11_AAA_HHH"]
    assert [p["status"] for p in kp["home"]] == ["Out"] and kp["away"] == []
    rec = C.record(both, C.grade(both, OUT, POINTS, set(), T2), {"2026_11_AAA_HHH": -7.0})
    assert (rec["claims"], rec["graded"], rec["mean_moved"]) == (1, 1, 1.0)
    assert rec["rows"][0]["margin_vs_line"] == -10.0  # lost by 7 as a 3-point favorite
    assert C.record(both.clear(), both.clear(), {}) is None


def test_availability_lists_top_starters_with_status_only_when_listed():
    c = _claims(_inj([("HHH", "h2", "Hal Two", "CB", "Questionable")]))
    a = C.availability(VALUES, c, PASSES.head(1), "HHH")
    assert [p["value_pts"] for p in a["players"]] == [1.2, 0.6, 0.3, 0.25]  # h5's role is too small
    assert a["players"][0]["status"] is None and a["players"][1]["status"] == "Questionable"
    assert a["value_at_risk"] == c["at_risk"].sum()


def test_the_lock_never_reads_the_claims():
    src = inspect.getsource(lock)
    assert "claims" not in src.replace("strong_calls", "")


def test_availability_reads_the_report_itself_before_any_claims_pass():
    # no pass has looked yet, but the report has a game status: the panel agrees with the game page
    report = [
        {"team": "HHH", "week": 11, "gsis_id": "h2", "pos": "CB", "status": "Out"},
        {"team": "HHH", "week": 11, "gsis_id": "h1", "pos": "WR", "status": "Questionable"},
        {"team": "HHH", "week": 10, "gsis_id": "h3", "pos": "T", "status": "Out"},  # last week
    ]
    empty = (pl.DataFrame(schema=C.SCHEMA), pl.DataFrame(schema=C.PASS_SCHEMA))
    a = C.availability(VALUES, *empty, "HHH", injuries=report, rates=RATES)
    assert a["reported"] and a["listed"] == []
    by = {p["value_pts"]: p for p in a["players"]}
    assert (by[0.6]["status"], by[0.6]["at_risk"]) == ("Out", 0.6)
    assert (by[1.2]["p_play"], by[1.2]["at_risk"]) == (0.73, round(1.2 * 0.27, 2))
    assert by[0.3]["status"] is None  # last week's Out is gone
    assert a["value_at_risk"] == round(0.6 + 1.2 * 0.27, 2)
    practice = [{**report[0], "status": None}]
    assert (
        C.availability(VALUES, *empty, "HHH", injuries=practice, rates=RATES)["value_at_risk"]
        is None
    )
