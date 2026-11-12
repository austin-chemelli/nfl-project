"""Market leans from the ledger (ADR 0028, M25.6): sign, point in time, grading, and never a forecast."""

import re
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from nfl import candidate_screen as screen
from nfl import leans, site

SRC = Path(__file__).resolve().parents[1] / "src" / "nfl"
IMPORTS = re.compile(
    r"from nfl import [^\n]*\bleans\b|import nfl\.leans|from nfl\.leans import|nfl\.leans\b"
)


def ledger(*rows: dict) -> pl.DataFrame:
    base = {
        "verdict": "use",
        "pregame": True,
        "resid_mk": 1.0,
        "resid_mk_lo": 0.5,
        "resid_mk_hi": 1.5,
    }
    return pl.DataFrame([base | r for r in rows])


def team_games(season=2025, weeks=8, seed=4) -> pl.DataFrame:
    """Four teams, one game a week each; every SUM_COL is random, sacks and dropbacks planted per team
    (A takes the fewest sacks, D the most)."""
    rng = np.random.default_rng(seed)
    rate = {"A": 0.03, "B": 0.06, "C": 0.08, "D": 0.11}
    rows = []
    for s in (season - 1, season):
        for w in range(1, weeks + 1):
            for t in "ABCD":
                r = {c: float(rng.random()) for c in screen.SUM_COLS}
                r |= {"game_id": f"{s}_{w}_{t}", "season": s, "week": w, "team": t, "games": 1.0}
                r |= {"o_db": 40.0, "o_sacks": 40.0 * (rate[t] + 0.01 * rng.normal())}
                rows.append(r)
    return pl.DataFrame(rows)


def leaner(rows: pl.DataFrame, led: pl.DataFrame) -> leans.Leaner:
    """A Leaner without a database: the team-games frame and the history of gaps set directly."""
    lr = leans.Leaner.__new__(leans.Leaner)
    lr.use = leans.use_rows(led)
    lr.tg = rows
    lr._hist = {}
    for c, _ in lr.use:
        xs = []
        for s in rows["season"].unique().to_list():
            for w in range(leans.MIN_WEEK, 9):
                for h, a in (("A", "D"), ("B", "C"), ("D", "A"), ("C", "B")):
                    vh, va = lr.team_value(c, s, w, h), lr.team_value(c, s, w, a)
                    xs.append((s - 1, vh - va))  # one season earlier, so the scale is history
        lr._hist[c.id] = pl.DataFrame(xs, schema=["season", "x"], orient="row")
    return lr


GAME = {"game_id": "g", "season": 2025, "week": 6, "home_team": "A", "away_team": "D"}


def test_no_use_candidate_means_no_lean():
    rows = team_games()
    assert leaner(rows, pl.DataFrame()).lean(GAME) is None
    assert leaner(rows, ledger({"candidate": "sack_off", "verdict": "none"})).lean(GAME) is None
    assert leaner(rows, ledger({"candidate": "sack_off", "pregame": False})).lean(GAME) is None


def test_a_lower_is_better_candidate_leans_toward_the_team_that_is_better_at_it():
    """sack_off is oriented by good = -1: A, which takes the fewest sacks, gets the lean at home, and
    the lean flips when A is away."""
    rows = team_games()
    lr = leaner(rows, ledger({"candidate": "sack_off"}))
    home = lr.lean(GAME)
    away = lr.lean(GAME | {"home_team": "D", "away_team": "A"})
    assert home.pts > 0 and home.side == "A"
    assert away.pts < 0 and away.side == "A"
    assert home.lo <= home.pts <= home.hi
    assert [p.candidate for p in home.parts] == ["sack_off"]


def test_lean_reads_only_earlier_weeks_and_none_before_min_week():
    rows = team_games()
    lr = leaner(rows, ledger({"candidate": "sack_off"}))
    base = lr.lean(GAME).to_dict()
    # the game's own week and later change nothing
    wild = rows.with_columns(
        pl.when((pl.col("season") == 2025) & (pl.col("week") >= 6))
        .then(39.0)
        .otherwise(pl.col("o_sacks"))
        .alias("o_sacks")
    )
    lr2 = leaner(rows, ledger({"candidate": "sack_off"}))
    lr2.tg = wild
    assert lr2.lean(GAME).to_dict() == base
    # an earlier week does
    lr2.tg = rows.with_columns(
        pl.when((pl.col("season") == 2025) & (pl.col("week") == 5) & (pl.col("team") == "A"))
        .then(39.0).otherwise(pl.col("o_sacks")).alias("o_sacks")
    )  # fmt: skip
    assert lr2.lean(GAME).to_dict() != base
    assert lr.lean(GAME | {"week": 3}) is None


@pytest.mark.parametrize(
    "pts,result,spread,want",
    [(1.0, 7, 3.0, "right"), (1.0, 1, 3.0, "wrong"), (-1.0, 1, 3.0, "right"), (1.0, 3, 3.0, "push"),
     (0.0, 7, 3.0, "push"), (1.0, None, 3.0, None), (1.0, 7, None, None)],
)  # fmt: skip
def test_grade_against_the_spread(pts, result, spread, want):
    lean = leans.Lean("g", 2026, 10, "A", "B", pts, pts - 1, pts + 1, "A")
    assert leans.grade(lean, result, spread) == want


def test_the_lean_never_reaches_a_forecast_writer():
    """predictions, bets, the scorecard, the lock and the README never import the leans."""
    writers = ["predict.py", "lock.py", "grade.py", "readme.py", "ledger.py", "strong_calls.py"]
    found = [f for f in writers if (SRC / f).exists()]
    assert found, "no writer modules found: the guard checks nothing"
    for f in found:
        assert not IMPORTS.search((SRC / f).read_text()), f
    for p in (SRC / "models").glob("*.py"):
        assert not IMPORTS.search(p.read_text()), p.name
    assert IMPORTS.search((SRC / "site.py").read_text())  # control: the pattern does find a reader


def test_site_lean_and_record():
    assert site.game_lean(None, GAME) is None
    rows = team_games()
    lr = leaner(rows, ledger({"candidate": "sack_off"}))
    g = GAME | {"season": 2025, "result": 10, "spread_line": 3.0}
    out = site.game_lean(lr, g)
    assert out["tracked"] is False and out["grade"] is None  # before 2026 Week 10
    tracked = [({}, {"tracked": True, "week": w, "pts": p, "grade": gr})
               for w, p, gr in ((10, 1.0, "right"), (10, -2.0, "wrong"), (11, 0.5, None))]  # fmt: skip
    rec = site.leans_record(
        tracked + [({}, None), ({}, {"tracked": False, "week": 9, "pts": 9.0, "grade": "right"})]
    )
    assert rec == {"from_season": 2026, "from_week": 10, "weeks_tracked": 2, "n": 2, "right": 1,
                   "wrong": 1, "push": 0, "mean_abs_pts": round(3.5 / 3, 2)}  # fmt: skip
    assert site.leans_record([({}, None)]) is None
    assert (
        site.leans_record(tracked, current_week=10)["weeks_tracked"] == 1
    )  # later weeks don't count yet
