"""Participation curation: personnel parsing, package / two-high mapping, team-code folding."""

import duckdb
import polars as pl

from nfl.curate import participation_select_sql

OFF = {
    "1 C, 2 G, 1 QB, 1 RB, 2 T, 1 TE, 3 WR": ("11", 1, 1, 3),
    "1 C, 2 G, 1 QB, 1 RB, 2 T, 2 TE, 2 WR": ("12", 1, 2, 2),
    "1 C, 1 FB, 2 G, 1 QB, 1 RB, 2 T, 1 TE, 1 WR": ("21", 2, 1, 1),  # FB counts as RB
    "1 C, 2 G, 1 QB, 1 RB, 2 T, 3 TE, 1 WR": ("13", 1, 3, 1),
    "1 C, 2 G, 1 QB, 2 RB, 2 T, 2 TE": ("22", 2, 2, 0),
    "1 C, 2 G, 1 QB, 1 RB, 2 T, 4 WR": ("10", 1, 0, 4),
    "6 OL, 1 RB, 2 TE, 1 WR": ("12", 1, 2, 1),
    "1 C, 2 G, 1 QB, 2 T, 5 WR": ("other", 0, 0, 5),
}
DEF = {
    "4 DL, 3 LB, 4 DB": ("base", 4),  # NGS style
    "4 DL, 2 LB, 5 DB": ("nickel", 5),
    "3 DL, 1 LB, 7 DB": ("dime", 7),
    "3 CB, 2 DE, 2 DT, 1 FS, 2 ILB, 1 SS": ("nickel", 5),  # FTN style
    "2 CB, 2 DE, 2 DT, 1 FS, 2 ILB, 1 OLB, 1 SS": ("base", 4),
}
COVER = {
    "COVER_2": True, "COVER_4": True, "COVER_6": True, "2_MAN": True,
    "COVER_0": False, "COVER_1": False, "COVER_3": False,
    "COMBO": None, "BLOWN": None, "COVER_9": None, None: None,
}  # fmt: skip


def _run(part_rows, plays_rows):
    con = duckdb.connect()
    part = pl.DataFrame(part_rows)
    plays = pl.DataFrame(plays_rows)
    con.register("part_df", part)
    con.register("plays_df", plays)
    return con.sql(participation_select_sql("part_df", "plays_df")).pl()


def _part(i, game="2024_01_AAA_BBB", poss="AAA", off=None, dfn=None, cov=None, mz=None, **kw):
    return {
        "nflverse_game_id": game, "play_id": float(i), "possession_team": poss,
        "offense_formation": "SHOTGUN", "offense_personnel": off,
        "defenders_in_box": 6, "defense_personnel": dfn, "number_of_pass_rushers": 4,
        "time_to_throw": 2.5, "was_pressure": False, "defense_man_zone_type": mz,
        "defense_coverage_type": cov, "raw_snapshot_ts": "t", **kw,
    }  # fmt: skip


def _play(i, game="2024_01_AAA_BBB", pos="AAA", dfn="BBB", home="BBB", away="AAA"):
    return {
        "game_id": game, "play_id": i, "week": 1, "posteam": pos, "defteam": dfn, "down": 1,
        "ydstogo": 10, "play_type": "pass", "pass": 1, "qb_dropback": 1, "shotgun": 1, "sack": 0,
        "passer_player_id": "p", "passer_player_name": "P", "epa": 0.1, "success": 1,
        "home_team": home, "away_team": away,
    }  # fmt: skip


def test_personnel_parsing_and_packages():
    offs, defs = list(OFF), list(DEF)
    n = max(len(offs), len(defs))
    part = [_part(i, off=offs[i % len(offs)], dfn=defs[i % len(defs)]) for i in range(n)]
    out = _run(part, [_play(i) for i in range(n)]).sort("play_id")
    for r in out.iter_rows(named=True):
        code, rb, te, wr = OFF[offs[r["play_id"] % len(offs)]]
        assert (r["off_personnel"], r["off_rb"], r["off_te"], r["off_wr"]) == (code, rb, te, wr)
        pkg, db = DEF[defs[r["play_id"] % len(defs)]]
        assert (r["def_package"], r["def_db"]) == (pkg, db)
        assert r["provider"] == "ftn"


def test_two_high_and_man_zone_mapping():
    covs = list(COVER)
    part = [
        _part(i, cov=c, mz=None if c is None else ("MAN_COVERAGE" if c in ("COVER_0", "COVER_1", "2_MAN") else "ZONE_COVERAGE"))
        for i, c in enumerate(covs)
    ]  # fmt: skip
    out = _run(part, [_play(i) for i in range(len(covs))]).sort("play_id")
    for r in out.iter_rows(named=True):
        assert r["two_high"] == COVER[covs[r["play_id"]]], covs[r["play_id"]]
    assert out["man_zone"].to_list()[:2] == ["ZONE", "ZONE"]
    assert out["man_zone"][-1] is None


def test_null_personnel_stays_null_and_provider_split():
    part = [
        _part(1, off=None, dfn=None),
        _part(2, game="2019_01_AAA_BBB", off="1 RB, 1 TE, 3 WR", dfn="4 DL, 3 LB, 4 DB"),
    ]
    plays = [_play(1), _play(2, game="2019_01_AAA_BBB")]
    out = _run(part, plays).sort("play_id")
    assert out["off_personnel"][0] is None and out["def_package"][0] is None
    assert out["provider"].to_list() == ["ftn", "ngs"]


def test_team_code_folding_2016_stl_game():
    # participation prints historical codes (STL / OAK); an unmatched play falls back to folded codes
    game = "2016_01_STL_OAK"
    part = [_part(1, game=game, poss="STL"), _part(2, game=game, poss="OAK")]
    plays = [_play(1, game=game, pos="LA", dfn="LV", home="OAK", away="STL")]
    out = _run(part, plays).sort("play_id")
    assert out["posteam"].to_list() == ["LA", "LV"]  # matched uses plays; unmatched is folded
    assert out["in_plays"].to_list() == [True, False]
    assert out["defteam"][0] == "LV" and out["defteam"][1] is None  # no plays row, no opponent
