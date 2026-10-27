"""QB features: projected starter, career shrinkage with season decay, trades, replacement level."""

from datetime import datetime

import polars as pl
import pytest

from nfl.features import qb, strength
from tests.test_strength import feat, games_frame, make_plays, play

R23 = -0.10  # fallback replacement before any earlier season exists
R_CPOE = -3.0


def dropback(gid, off, deff, passer, epa, cpoe=None, name=None):
    return play(
        gid, off, deff, 0.0, passer_player_id=passer, passer_player_name=name or passer,
        qb_epa=epa, cpoe=cpoe,
    )  # fmt: skip


# X: A in 2023, then traded to B. Y: B in 2023, then traded to A. Z: A's backup in g1 (1 dropback).
ROWS = [
    dropback("g1", "A", "B", "X", 0.2, 2.0), dropback("g1", "A", "B", "X", 0.4),
    dropback("g1", "A", "B", "Z", -0.5),
    dropback("g1", "B", "A", "Y", -0.1, -1.0), dropback("g1", "B", "A", "Y", -0.3),
    dropback("g1", "B", "A", "Y", 0.1),
    dropback("g2", "B", "A", "Y", 0.0), dropback("g2", "B", "A", "Y", 0.0),
    dropback("g2", "A", "B", "X", 0.6),
    dropback("g3", "A", "B", "Y", -0.2), dropback("g3", "A", "B", "Y", 0.2),
    dropback("g3", "B", "A", "X", 0.5),
    dropback("g4", "A", "B", "Y", 0.1),
    dropback("g4", "B", "A", "X", 0.3),
]  # fmt: skip


def run(rows=ROWS, games=None):
    games = games if games is not None else games_frame()
    tg = strength.team_games(games).with_columns(strength._canon().alias("ckey"))
    return qb.compute(tg, make_plays(rows)), tg


def shrunk(sx, n, repl, n0=250.0):
    return (sx + n0 * repl) / (n + n0)


def test_week1_is_replacement_and_follows_the_career():
    vals, _ = run()
    # nothing earlier: replacement fallback exactly
    assert feat(vals, "g1", "A", "strength.qb_epa") == pytest.approx(R23)
    assert feat(vals, "g1", "B", "strength.qb_cpoe") == pytest.approx(R_CPOE)
    # g2: A's starter is X (2 dropbacks beat Z's 1); he has g1 only: 0.6 over 2 dropbacks
    assert feat(vals, "g2", "A", "strength.qb_epa") == pytest.approx(shrunk(0.6, 2, R23))
    assert feat(vals, "g2", "B", "strength.qb_epa") == pytest.approx(shrunk(-0.3, 3, R23))
    # CPOE counts only non-null observations: X has one (2.0), Y has one (-1.0)
    assert feat(vals, "g2", "A", "strength.qb_cpoe") == pytest.approx(shrunk(2.0, 1, R_CPOE))
    assert feat(vals, "g2", "B", "strength.qb_cpoe") == pytest.approx(shrunk(-1.0, 1, R_CPOE))


def test_qb_follows_a_trade_with_seasonal_decay_and_pooled_replacement():
    vals, _ = run()
    # replacement for 2024 would be the pooled 2023 mean of QBs with < 250 career dropbacks, but
    # the toy pool has 9 dropbacks (< MIN_REPL_N) so the fallback applies (pooling: see the
    # replacement-level test); the same holds for the 2 CPOE observations
    r = R23
    # g3: X (now at B) brings his A-era 2023 numbers, weighted 0.75; Y (now at A) his B-era ones
    assert feat(vals, "g3", "B", "strength.qb_epa") == pytest.approx(
        shrunk(0.75 * 1.2, 0.75 * 3, r)
    )
    assert feat(vals, "g3", "A", "strength.qb_epa") == pytest.approx(
        shrunk(0.75 * -0.3, 0.75 * 5, r)
    )
    assert feat(vals, "g3", "B", "strength.qb_cpoe") == pytest.approx(
        shrunk(0.75 * 2.0, 0.75 * 1, R_CPOE)
    )
    # g4: this season's g3 is added at weight 1
    assert feat(vals, "g4", "B", "strength.qb_epa") == pytest.approx(shrunk(0.9 + 0.5, 2.25 + 1, r))
    assert feat(vals, "g4", "A", "strength.qb_epa") == pytest.approx(
        shrunk(-0.225 + 0.0, 3.75 + 2, r)
    )


def test_upcoming_game_uses_the_previous_games_passer_and_unknown_teams_are_null():
    vals, _ = run()
    # g5 (A vs C, not played): A's starter is g4's Y; Y's 2024 games are g3 and g4
    r = R23
    expect = shrunk(0.75 * -0.3 + (-0.2 + 0.2 + 0.1), 0.75 * 5 + 3, r)
    assert feat(vals, "g5", "A", "strength.qb_epa") == pytest.approx(expect)
    assert feat(vals, "g5", "C", "strength.qb_epa") is None
    assert feat(vals, "g5", "C", "strength.qb_cpoe") is None


def test_starter_is_the_first_passer_and_names_are_kept():
    _, tg = run()
    st = qb.projected_starters(tg, make_plays([*ROWS]))
    row = st.filter((pl.col("game_id") == "g1") & (pl.col("team") == "A"))
    assert row["qb"][0] == "X"
    named = qb.projected_starters(
        tg, make_plays([dropback("g1", "A", "B", "X", 0.1, name="P.Mahomes")])
    )
    assert named.filter((pl.col("game_id") == "g1") & (pl.col("team") == "A"))["qb_name"][0] == (
        "P.Mahomes"
    )


def test_starter_hurt_early_is_still_the_projected_starter():
    """Leakage guard (found 2026-10-27): if the starter leaves after one dropback and the backup
    throws the rest, the pregame starter is still the starter. Using the passer with the most
    dropbacks leaked in-game injuries into a pregame feature."""
    _, tg = run()
    rows = [dropback("g1", "A", "B", "X", 0.2)] + [dropback("g1", "A", "B", "Z", -0.5)] * 5
    st = qb.projected_starters(tg, make_plays(rows))
    assert st.filter((pl.col("game_id") == "g1") & (pl.col("team") == "A"))["qb"][0] == "X"


def test_replacement_level_pools_only_low_career_qbs_from_earlier_seasons():
    def row(q, season, n_db, sx_e, n_e, sx_c, n_c):
        return (q, season, float(n_db), sx_e, float(n_e), sx_c, float(n_c))

    qs = pl.DataFrame(
        [
            row("vet", 2019, 400, 80.0, 400, 400.0, 300),  # 400 dropbacks: not replacement
            row("bench", 2019, 120, -24.0, 120, -480.0, 120),  # 120: replacement
            row("rook", 2019, 80, -12.0, 80, -240.0, 80),
            row("bench", 2020, 90, 9.0, 90, 90.0, 90),  # 210 career through 2020: still < 250
            row("vet", 2021, 500, 500.0, 500, 500.0, 500),  # later season: ignored for 2021
        ],
        schema=["qb", "season", "n_db", "sx_e", "n_e", "sx_c", "n_c"],
        orient="row",
    )
    out = qb._replacement(qs, [2019, 2020, 2021]).sort("season")
    assert out["_re"][0] == pytest.approx(-0.10)  # nothing earlier than 2019: fallback
    assert out["_rc"][0] == pytest.approx(-3.0)
    # 2020: bench + rook from 2019 -> (-24 - 12) / 200 = -0.18; CPOE (-720) / 200 = -3.6
    assert out["_re"][1] == pytest.approx(-0.18)
    assert out["_rc"][1] == pytest.approx(-3.6)
    # 2021: bench's career is 210 (< 250) and includes 2020; the vet (400) stays out
    assert out["_re"][2] == pytest.approx((-24 - 12 + 9) / 290)
    # too few observations (< 100) falls back
    tiny = qs.filter(pl.col("qb") == "rook")
    assert qb._replacement(tiny, [2020])["_re"][0] == pytest.approx(-0.10)


def test_target_game_values_do_not_move_its_own_features():
    games = games_frame()
    base, _ = run(ROWS, games)
    changed = [
        {**p, "qb_epa": 9.0, "cpoe": 9.0} if p["game_id"] in ("g4", "g5") else p
        for p in [dict(zip(make_plays([r]).columns, make_plays([r]).row(0))) for r in ROWS]
    ]
    moved, _ = run(changed, games)
    for gid in ("g1", "g2", "g3", "g4"):
        for team in ("A", "B"):
            for f in ("strength.qb_epa", "strength.qb_cpoe"):
                assert feat(base, gid, team, f) == feat(moved, gid, team, f), (gid, team, f)
    assert feat(base, "g5", "A", "strength.qb_epa") != feat(moved, "g5", "A", "strength.qb_epa")
    assert datetime  # silence unused import in minimal envs
