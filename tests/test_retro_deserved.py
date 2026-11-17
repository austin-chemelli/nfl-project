"""The deserved-to-win meter (nfl.retro.deserved): garbage time, the factors, the fit, the record."""

import json
import random

import polars as pl
import pytest

from nfl.retro import deserved as D
from nfl.retro.daily import expectations_stale
from nfl.retro.schema import DeservedFit
from tests.test_retro_game import G1, G2, base_plays, build_games, read, target_plays, write_tree

LOST = 0.5
COLS = {
    "game_id": pl.Utf8, "play_id": pl.Float64, "posteam": pl.Utf8, "play_type": pl.Utf8,
    "epa": pl.Float64, "success": pl.Float64, "wp": pl.Float64, "down": pl.Float64,
    "interception": pl.Float64, "fumble": pl.Float64, "fumble_lost": pl.Float64,
    "fixed_drive": pl.Float64, "yardline_100": pl.Float64, "qtr": pl.Float64,
    "game_seconds_remaining": pl.Float64, "home_team": pl.Utf8, "away_team": pl.Utf8,
}  # fmt: skip
_id = [0]


def p(gid="g", pos="H", **kw):
    _id[0] += 1
    row = dict.fromkeys(COLS) | {
        "game_id": gid, "play_id": float(_id[0]), "posteam": pos, "play_type": "pass",
        "epa": 0.0, "success": 0.0, "wp": 0.5, "down": 1.0, "fixed_drive": 1.0,
        "yardline_100": 75.0, "home_team": "H", "away_team": "A",
    }  # fmt: skip
    return row | kw


def df(rows):
    return pl.DataFrame(rows, schema=COLS)


@pytest.mark.parametrize(
    "wp, w",
    [(0.5, 1.0), (0.05, 1.0), (0.95, 1.0), (0.03, 0.625), (0.97, 0.625), (0.01, 0.25), (0.999, 0.25), (None, 1.0)],
)  # fmt: skip
def test_garbage_weight(wp, w):
    got = pl.DataFrame({"wp": [wp]}, schema={"wp": pl.Float64}).select(D.garbage_weight())["w"][0]
    assert got == pytest.approx(w)


def test_factors_drop_garbage_time_and_turnover_plays():
    rows = [
        p(epa=0.4, success=1.0),
        p(epa=-0.2),
        p(epa=-6.0, interception=1.0),  # a giveaway, not efficiency
        p(epa=-4.0, fumble=1.0, fumble_lost=1.0),  # counts as half a giveaway (LOST = 0.5)
        p(epa=-1.0, fumble=1.0, fumble_lost=0.0),  # recovered: still half a giveaway
        p(epa=9.0, wp=0.005, fumble=1.0, down=3.0),  # garbage time: counts a quarter
    ]
    r = D.team_factors(df(rows), LOST).row(0, named=True)
    assert r["efficiency"] == pytest.approx((0.4 - 0.2 - 1.0 + 0.25 * 9.0) / 3.25)
    assert r["giveaways"] == pytest.approx(1 + 0.5 + 0.5 + 0.25 * 0.5)
    assert r["third_share"] == pytest.approx(0.25 / 5.25)
    assert r["success"] == pytest.approx(1 / 5.25)


def test_scoring_chances_by_drive_weighted_by_first_snap():
    rows = [
        p(fixed_drive=1.0, yardline_100=60.0), p(fixed_drive=1.0, yardline_100=38.0),  # a chance
        p(fixed_drive=2.0, yardline_100=80.0, play_type="punt"),  # no chance
        p(fixed_drive=3.0, yardline_100=30.0, play_type="field_goal"),  # a chance
        p(fixed_drive=4.0, yardline_100=20.0, wp=0.005),  # garbage time: counts a quarter
    ]  # fmt: skip
    r = D.team_factors(df(rows), LOST).row(0, named=True)
    assert r["chances"] == pytest.approx(2.25 / 3.25)
    assert r["drives"] == 4 and r["chance_drives"] == 3


def _season(n_games, seed=1):
    """Synthetic games whose margin is planted on the three factors."""
    rng = random.Random(seed)
    plays, games = [], []
    for i in range(n_games):
        gid = f"s{i}"
        e_h, e_a = rng.gauss(0, 0.15), rng.gauss(0, 0.15)
        c_h, c_a = rng.randint(1, 9), rng.randint(1, 9)
        g_h, g_a = rng.randint(0, 3), rng.randint(0, 3)
        for team, e, c, gv in (("H", e_h, c_h, g_h), ("A", e_a, c_a, g_a)):
            for d in range(10):
                plays.append(p(gid, team, epa=e, fixed_drive=float(d), yardline_100=30.0 if d < c else 70.0))  # fmt: skip
            for _ in range(gv):
                plays.append(p(gid, team, epa=-5.0, interception=1.0, fixed_drive=0.0))
        margin = 30 * (e_h - e_a) + 10 * (c_h - c_a) / 10 - 3 * (g_h - g_a) + rng.gauss(0, 2)
        games.append({"game_id": gid, "home_score": 20 + round(margin), "away_score": 20})
    return df(plays), pl.DataFrame(games)


def test_fit_recovers_planted_weights_and_needs_enough_games():
    plays, games = _season(400)
    f = D.fit(plays, games, LOST)
    assert f.b_efficiency == pytest.approx(30, rel=0.1)
    assert f.b_chances == pytest.approx(10, rel=0.15)
    assert f.b_giveaways == pytest.approx(-3, rel=0.15)
    assert (
        f.k > 0
        and f.n == 400
        and (f.wp_full, f.wp_zero, f.wp_floor) == (D.WP_FULL, D.WP_ZERO, 0.25)
    )
    small_p, small_g = _season(D.MIN_GAMES - 1)
    assert D.fit(small_p, small_g, LOST) is None


FIT = DeservedFit(b_efficiency=30, b_chances=10, b_giveaways=-3, k=0.4, sigma=7, r2=0.75, n=1, wp_full=0.05, wp_zero=0.01)  # fmt: skip


def _game(hs, as_):
    return {"home_team": "HOM", "away_team": "AWY", "home_score": hs, "away_score": as_}


def test_meter_adds_up_and_is_symmetric():
    rows = [p(pos="H", epa=0.3, yardline_100=30.0) for _ in range(10)]
    rows += [p(pos="A", epa=0.0, fixed_drive=2.0) for _ in range(10)]
    rows += [p(pos="A", epa=-5.0, interception=1.0, fixed_drive=2.0)]
    m = D.deserved(FIT, df(rows), _game(17, 20), "H", "A", LOST)
    weighted = [f for f in m.factors if f.weighted]
    assert [f.factor for f in weighted] == ["efficiency", "chances", "giveaways"]
    assert m.margin_home == pytest.approx(sum(f.pts for f in weighted), abs=0.11)
    assert m.margin_home == pytest.approx(30 * 0.3 + 10 * 1.0 - 3 * -1.0, abs=0.05)
    assert m.winner == "HOM" and m.p_home > 0.99 and m.matches_result is False
    assert m.gap_home == pytest.approx(-3 - m.margin_home, abs=0.11)
    assert m.sentence.startswith("HOM deserved to win: 99%") and "but AWY won by 3" in m.sentence
    assert all(not f.weighted and f.pts is None for f in m.factors if f.factor in ("success", "third_share"))  # fmt: skip
    # the same plays with the teams' roles swapped: the mirror image (no home field)
    flip = D.deserved(FIT, df(rows), _game(20, 17), "A", "H", LOST)
    assert flip.p_home == pytest.approx(1 - m.p_home, abs=1e-4)
    assert flip.margin_home == pytest.approx(-m.margin_home)


def test_toss_up_and_garbage_clock():
    rows = [p(pos="H", epa=0.01) for _ in range(5)] + [p(pos="A", epa=0.0) for _ in range(5)]
    rows += [p(pos="H", epa=0.5, wp=0.997, qtr=4.0, game_seconds_remaining=200.0)]
    rows += [p(pos="A", epa=0.5, wp=0.004, qtr=4.0, game_seconds_remaining=150.0)]
    m = D.deserved(FIT, df(rows), _game(10, 10), "H", "A", LOST)
    assert m.sentence.startswith("A toss-up on the plays") and "tied 10-10" in m.sentence
    assert m.matches_result is None
    assert (m.garbage_t, m.garbage_clock) == (3400, "Q4 3:20")
    assert (m.snaps, m.snaps_full) == (12, 10)


def test_applies_only_after_the_fit_window():
    assert D.applies_to((2015, 2025), 2026)
    assert not D.applies_to((2015, 2025), 2025)
    assert not D.applies_to((2015, 2026), 2026)


def test_record_has_the_meter_and_none_inside_the_window(tmp_path):
    tree = write_tree(tmp_path, [G1, G2], base_plays("g1") + target_plays())
    build_games(tree, 2026)
    rec = read(tree, "g2")
    assert rec["deserved"]["winner"] in ("HOM", "AWY")
    assert not any(h.startswith("Teams that played") for h in rec["headlines"])
    f = tree.marts / "retro" / "expectations.json"
    e = json.loads(f.read_text()) | {"seasons": [2015, 2026]}  # a fit that saw 2026
    f.write_text(json.dumps(e))
    build_games(tree, 2026, force=True)
    rec = read(tree, "g2")
    assert rec["deserved"] is None
    assert any(h.startswith("Teams that played") for h in rec["headlines"])


def test_expectations_stale(tmp_path):
    from nfl.config import Paths
    from nfl.retro.expectations import VERSION, expectations_path

    paths = Paths(tmp_path)
    assert expectations_stale(paths)  # missing
    f = expectations_path(paths)
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"version": "retro_exp_v2"}))
    assert expectations_stale(paths)
    f.write_text(json.dumps({"version": VERSION}))
    assert not expectations_stale(paths)
