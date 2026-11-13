"""Team health (M24.7): the full-strength lineup since March, values from before an injury, reserve
lists with their window, and the outlook."""

from datetime import datetime

import polars as pl

from nfl.players import health as H

NOW = datetime(2026, 11, 12, 12, 0)
MARCH, SEPT, NOV = "2026-03-22T06:00:00Z", "2026-09-05T12:00:00Z", "2026-11-10T15:00:00Z"
O, D = "3WR 1TE", "Base 3-4 D"


def _chart(dt, rows):
    return [
        {"team": "HHH", "dt": dt, "pos_grp": g, "pos_abb": a, "pos_slot": s, "pos_rank": r,
         "gsis_id": i, "player_name": n} for g, a, s, r, i, n in rows
    ]  # fmt: skip


DEPTH = pl.DataFrame(
    _chart("2025-12-01T00:00:00Z", [(O, "LT", 1, 1, "ancient", "Last Season LT")])
    + _chart(MARCH, [
        (O, "LT", 1, 1, "tunsil", "Hurt In Camp"), (O, "LT", 1, 2, "backup_lt", "Backup LT"),
        (O, "WR", 1, 1, "star", "Star WR"), (O, "WR", 2, 2, "w2", "W Two"), (O, "WR", 8, 3, "w3", "W Three"),
        (O, "QB", 9, 1, "qb", "Q B"), (D, "NT", 4, 1, "nose", "Nose"), (O, "TE", 3, 1, "cut_te", "Cut TE"),
    ])
    + _chart(NOV, [
        (O, "LT", 1, 1, "backup_lt", "Backup LT"),
        (O, "WR", 1, 1, "w2", "W Two"), (O, "WR", 2, 2, "w3", "W Three"), (O, "WR", 8, 3, "w4", "W Four"),
        (O, "QB", 9, 1, "qb", "Q B"), (D, "NT", 4, 1, "nose2", "Nose Two"), (O, "TE", 3, 1, "te2", "New TE"),
    ])
)  # fmt: skip

ROSTERS = pl.DataFrame(
    [
        {"team": "HHH", "week": w, "gsis_id": g, "status": st, "status_description_abbr": c}
        for w in (8, 9, 10)
        for g, st, c in [
            ("tunsil", "RES", "R01"), ("backup_lt", "ACT", "A01"), ("w2", "ACT", "A01"),
            ("w3", "ACT", "A01"), ("w4", "ACT", "A01"), ("qb", "ACT", "A01"),
            ("nose2", "ACT", "A01"), ("te2", "ACT", "A01"),
            ("star", "RES" if w >= 9 else "ACT", "R01" if w >= 9 else "A01"),
            ("nose", "RES" if w >= 10 else "ACT", "R01" if w >= 10 else "A01"),
        ]
    ]
)  # fmt: skip


class Values(H.HealthyValues):
    """Fixed values: the test isn't about the value model."""

    def __init__(self, vals):
        self.vals = vals

    def at(self, season, week, ids):
        return {g: self.vals[g] for g in ids if g in self.vals}


VALS = Values({
    g: {"value_pts": v, "grp": grp} for g, v, grp in [
        ("tunsil", 0.5, "OL"), ("backup_lt", 0.1, "OL"), ("star", 1.2, "WR"), ("w2", 0.6, "WR"),
        ("w3", 0.3, "WR"), ("w4", 0.05, "WR"), ("qb", 4.0, "QB"), ("nose", 0.5, "DL"),
        ("nose2", 0.1, "DL"), ("cut_te", 0.9, "TE"), ("te2", 0.2, "TE"), ("ancient", 2.0, "OL"),
    ]
})  # fmt: skip
INJ = [{"team": "HHH", "week": 11, "gsis_id": "w2", "pos": "WR", "status": "Questionable"}]
RATES = {("Questionable", "WR"): (0.75, 1000)}


def _week():
    return H.team_week(DEPTH, "HHH", 2026, 11, NOW, ROSTERS, INJ, VALS, RATES)


def test_full_strength_is_the_best_starter_since_march_still_on_the_team():
    s = {x["slot"]: x for x in _week()["starters"]}
    assert s["LT"]["player"] == "Hurt In Camp" and s["LT"]["replaced_by"] == "Backup LT"
    assert s["NT"]["player"] == "Nose" and s["NT"]["replaced_by"] == "Nose Two"
    # the WR room in value order; the star keeps WR1 though the chart has moved him off it
    assert [s[k]["player"] for k in ("WR1", "WR2", "WR3")] == ["Star WR", "W Two", "W Three"]
    # last season's chart doesn't count, nor a player no longer on the roster
    assert "Last Season LT" not in {x["player"] for x in s.values()}
    assert s["TE"]["player"] == "New TE" and s["TE"]["replaced_by"] is None


def test_reserve_list_windows_and_report_statuses():
    s = {x["player"]: x for x in _week()["starters"]}
    camp, star, nose = s["Hurt In Camp"], s["Star WR"], s["Nose"]
    assert (camp["status"], camp["since_week"], camp["eligible_week"]) == ("IR", 8, 12)
    assert (star["since_week"], star["eligible_week"], star["missing_pts"]) == (9, 13, 1.2)
    assert (nose["since_week"], nose["eligible_week"]) == (10, 14)
    assert (s["W Two"]["status"], s["W Two"]["p_play"], s["W Two"]["missing_pts"]) == ("Questionable", 0.75, 0.15)  # fmt: skip
    assert s["Q B"]["status"] is None and s["Q B"]["missing_pts"] == 0


def test_health_totals_and_groups():
    w = _week()
    assert w["full_pts"] == round(0.5 + 1.2 + 0.6 + 0.3 + 4.0 + 0.5 + 0.2, 2)
    assert w["missing_pts"] == round(0.5 + 1.2 + 0.15 + 0.5, 2)
    assert w["health"] == round(1 - w["missing_pts"] / w["full_pts"], 3)
    wr = next(g for g in w["groups"] if g["grp"] == "WR")
    assert (wr["full_pts"], wr["missing_pts"]) == (2.1, 1.35)


def test_outlook_brings_players_back_when_eligible_and_not_before():
    w = _week()
    o = {x["week"]: x["missing_pts"] for x in H.outlook(w, [12, 13, 14])}
    # wk 12: the Questionable WR is back, the camp injury is eligible; 13 the star; 14 the nose
    assert o == {12: round(1.2 + 0.5, 2), 13: 0.5, 14: 0}


def test_a_player_past_his_window_stays_out_in_the_outlook():
    w = {**_week(), "week": 13}
    camp = next(s for s in w["starters"] if s["player"] == "Hurt In Camp")
    assert camp["eligible_week"] == 12
    o = H.outlook({**w, "starters": [camp]}, [14, 15])
    assert [x["missing_pts"] for x in o] == [0.5, 0.5]


def test_healthy_values_use_the_week_of_his_last_game():
    """A player who missed the team's last game is valued as of the week he last played."""

    class Slices(H.HealthyValues):
        def slice(self, season, week):
            return {"hurt": {"gsis_id": "hurt", "value_pts": 1.0 if week <= 7 else 0.4},
                    "fit": {"gsis_id": "fit", "value_pts": 0.8 if week == 11 else 0.1}}  # fmt: skip

    pg = pl.DataFrame({
        "season": [2026] * 6, "week": [5, 6, 7, 8, 9, 10], "team": ["HHH"] * 6,
        "gsis_id": ["hurt", "hurt", "hurt", "fit", "fit", "fit"],
    })  # fmt: skip
    v = Slices(pg, pl.DataFrame()).at(2026, 11, ["hurt", "fit"])
    assert v["hurt"]["value_pts"] == 1.0 and v["hurt"]["valued_week"] == (2026, 7)
    assert v["fit"]["value_pts"] == 0.8  # played the team's last game: the current value


def test_a_healthy_player_the_chart_moved_down_lost_the_job_and_isnt_missing():
    """The benched former QB1 is on the roster and active: the current starter keeps full strength,
    so the starter's own injury shows."""
    depth = pl.concat([DEPTH, pl.DataFrame(_chart(MARCH, [(O, "QB", 9, 1, "vet", "Benched Vet")]))])  # fmt: skip
    ros = pl.concat([ROSTERS, pl.DataFrame([{"team": "HHH", "week": 10, "gsis_id": "vet", "status": "ACT", "status_description_abbr": "A01"}])])  # fmt: skip
    vals = Values({**VALS.vals, "vet": {"value_pts": 5.0, "grp": "QB"}})
    inj = [*INJ, {"team": "HHH", "week": 11, "gsis_id": "qb", "pos": "QB", "status": "Out"}]
    w = H.team_week(depth, "HHH", 2026, 11, NOW, ros, inj, vals, RATES)
    qb = next(s for s in w["starters"] if s["slot"] == "QB")
    assert (qb["player"], qb["status"], qb["missing_pts"]) == ("Q B", "Out", 4.0)
    assert w["reported"]


def test_the_ir_window_counts_games_not_weeks():
    weeks = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15]  # a bye in week 11
    assert H.eligible_week(10, weeks) == 15  # misses 10, 12, 13, 14
    assert H.eligible_week(7, weeks) == 12  # misses 7, 8, 9, 10
    assert H.eligible_week(1, weeks) is None  # IR from camp: no window
    assert H.eligible_week(13, weeks) is None  # the season ends first


def test_wr_replacements_only_name_a_receiver_who_was_left_out():
    w = _week()
    wr = {s["player"]: s["replaced_by"] for s in w["starters"] if s["slot"].startswith("WR")}
    assert wr == {"Star WR": "W Four", "W Two": None, "W Three": None}
