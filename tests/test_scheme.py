"""Scheme rates on a tiny synthetic frame, plus one local-data sanity check."""

import duckdb
import polars as pl

from nfl.scheme import qb_scenarios_sql, rates_sql, team_season_rates
from tests.conftest import DATA, requires_data


def _row(posteam, defteam, **kw):
    base = {
        "season": 2024, "posteam": posteam, "defteam": defteam, "in_plays": True,
        "play_type": "pass", "pass": 1, "qb_dropback": 1, "shotgun": True,
        "off_personnel": "11", "off_rb": 1, "off_te": 1, "def_package": "nickel",
        "number_of_pass_rushers": 4, "was_pressure": False, "time_to_throw": 2.5,
        "man_zone": "ZONE", "coverage": "COVER_3", "two_high": False, "epa": 0.0,
        "success": 0, "passer_player_id": "q1", "passer_player_name": "Q One",
    }  # fmt: skip
    return {**base, **kw}


def _frame():
    rows = [
        _row("A", "B", man_zone="MAN", coverage="COVER_1", epa=1.0, success=1),
        _row("A", "B", man_zone="MAN", coverage="COVER_1", epa=-1.0, success=0),
        _row("A", "B", man_zone="ZONE", coverage="COVER_2", two_high=True, epa=0.5, success=1,
             number_of_pass_rushers=5, was_pressure=True, off_personnel="12", off_te=2),
        _row("A", "B", play_type="run", **{"pass": 0}, qb_dropback=0, man_zone=None, coverage=None,
             two_high=None, epa=0.2, success=1, time_to_throw=None, was_pressure=None,
             number_of_pass_rushers=None),
        _row("A", "B", passer_player_id="q2", passer_player_name="Q Two", epa=0.3, success=1),
        _row("A", "B", passer_player_id="q2", passer_player_name="Q Two", epa=0.1, success=1),
        _row("A", "B", passer_player_id="q2", passer_player_name="Q Two", epa=0.2, success=1),
    ]  # fmt: skip
    return pl.DataFrame(rows)


def _rates():
    con = duckdb.connect()
    con.register("t", _frame())
    return {(r["side"], r["metric"]): r for r in con.sql(rates_sql("t")).pl().iter_rows(named=True)}


def test_defense_rates_and_n():
    r = _rates()
    # 6 charted dropbacks: 2 man, 4 zone; one 5-man rush
    assert r["def", "man_rate"]["n"] == 6 and abs(r["def", "man_rate"]["rate"] - 2 / 6) < 1e-9
    assert abs(r["def", "two_high_rate"]["rate"] - 1 / 6) < 1e-9
    assert r["def", "blitz_rate"]["n"] == 6 and abs(r["def", "blitz_rate"]["rate"] - 1 / 6) < 1e-9
    assert abs(r["def", "cover_1_share"]["rate"] - 2 / 6) < 1e-9
    covers = [m for (s, m) in r if s == "def" and m.startswith("cover_") and m.endswith("_share")]
    assert abs(sum(r["def", m]["rate"] for m in covers) - 1) < 1e-9
    assert abs(r["def", "nickel_share"]["rate"] - 1.0) < 1e-9


def test_offense_rates_and_splits():
    r = _rates()
    assert r["off", "pers_11_share"]["n"] == 7
    assert abs(r["off", "pers_11_share"]["rate"] - 6 / 7) < 1e-9
    assert abs(r["off", "pers_heavy_share"]["rate"] - 1 / 7) < 1e-9
    assert abs(r["off", "pass_rate_11"]["rate"] - 5 / 6) < 1e-9  # one run among 6 '11' plays
    assert r["off", "epa_vs_man"]["n"] == 2 and r["off", "epa_vs_man"]["rate"] == 0.0
    assert r["off", "epa_vs_two_high"]["n"] == 1
    assert r["off", "epa_vs_pressure"]["n"] == 1 and r["off", "epa_vs_pressure"]["rate"] == 0.5
    assert r["off", "epa_vs_no_pressure"]["n"] == 5
    assert abs(r["off", "time_to_throw"]["rate"] - 2.5) < 1e-9


def test_primary_passer_is_most_dropbacks():
    con = duckdb.connect()
    con.register("t", _frame())
    q = con.sql(qb_scenarios_sql("t")).pl().filter(pl.col("side") == "off")
    assert q.height == 1  # q1 has 3 dropbacks (rows 1-3), q2 has 3: q1 wins the tie by id
    assert q["passer_player_id"][0] == "q1" and q["qb_dropbacks"][0] == 3
    assert q["n_all"][0] == 3 and q["n_man"][0] == 2


@requires_data
def test_kc_2024_defense_real_data():
    if not DATA.curated_table("participation").exists():
        import pytest

        pytest.skip("needs curated participation")
    df = team_season_rates(DATA).filter(
        (pl.col("season") == 2024) & (pl.col("team") == "KC") & (pl.col("side") == "def")
    )
    d = {m: v for m, v in zip(df["metric"], df["rate"], strict=True)}
    assert 0.05 < d["man_rate"] < 0.6
    covers = ["0", "1", "2", "3", "4", "6", "2_man", "other"]
    assert abs(sum(d[f"cover_{c}_share"] for c in covers) - 1) < 1e-6
