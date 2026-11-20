"""M23.5 decomposition members: noto EPA, takeaway rate, fumble luck, one-score luck."""

from datetime import datetime, timedelta

import duckdb
import polars as pl
import pytest

from nfl.features import decisions, strength
from nfl.tendencies import weekly_aggregates
from tests import test_decisions as td
from tests import test_strength as ts

NEW_STRENGTH = [
    "strength.epa_off_noto",
    "strength.epa_def_noto",
    "strength.takeaway_rate",
    "strength.fum_luck",
]


def with_flags(plays: pl.DataFrame, **cols) -> pl.DataFrame:
    return plays.with_columns(
        pl.lit(0.0).alias("interception"),
        pl.lit(0.0).alias("fumble"),
        pl.lit(0.0).alias("fumble_lost"),
    ).with_columns(**{k: v for k, v in cols.items()})


def planted(game_id="g1", off="A", deff="B", epa=-5.0):
    """One extra play: a lost fumble by `off`'s offense with a big negative EPA."""
    return pl.DataFrame(
        [
            {
                "game_id": game_id, "posteam": off, "defteam": deff, "play_type": "run",
                "epa": epa, "success": 0.0, "down": 1.0, "wp": 0.5, "is_pass": 0.0,
                "sack": 0.0, "qb_dropback": 0.0, "special_teams_play": 0.0,
                "interception": 0.0, "fumble": 1.0, "fumble_lost": 1.0,
            }
        ],
        schema={**ts.PLAY_SCHEMA, "interception": pl.Float64, "fumble": pl.Float64,
                "fumble_lost": pl.Float64},
    )  # fmt: skip


def test_planted_lost_fumble_moves_epa_but_not_noto():
    games = ts.games_frame()
    base = with_flags(ts.plays_frame())
    mut = pl.concat([base, planted()], how="diagonal_relaxed")
    a = strength.compute(games, base)
    b = strength.compute(games, mut)
    f = ts.feat
    # g2: B defended A's g1 plays; A's offense had the fumble
    assert f(b, "g2", "B", "strength.epa_def") != pytest.approx(f(a, "g2", "B", "strength.epa_def"))
    assert f(b, "g2", "A", "strength.epa_off") != pytest.approx(f(a, "g2", "A", "strength.epa_off"))
    for g, t, n in (("g2", "B", "epa_def_noto"), ("g2", "A", "epa_off_noto")):
        assert f(b, g, t, f"strength.{n}") == pytest.approx(f(a, g, t, f"strength.{n}"))
    # exact: noto def of B = A's three non-fumble plays, shrunk to the 0 prior
    assert f(b, "g2", "B", "strength.epa_def_noto") == pytest.approx(ts.shrunk(0.9, 3, 0.0))
    # takeaways: 1 in 4 plays against B, prior 0.025 with n0 = 1200
    assert f(b, "g2", "B", "strength.takeaway_rate") == pytest.approx(
        (1 + 1200 * 0.025) / (4 + 1200)
    )
    assert f(a, "g2", "B", "strength.takeaway_rate") == pytest.approx(1200 * 0.025 / (3 + 1200))
    # fum_luck: null before a first game; A lost its own fumble, B recovered it
    assert f(b, "g1", "A", "strength.fum_luck") is None
    assert f(b, "g2", "A", "strength.fum_luck") == pytest.approx(0.5 - 1.0)
    assert f(b, "g2", "B", "strength.fum_luck") == pytest.approx(1.0 - 0.5)
    assert f(a, "g2", "B", "strength.fum_luck") == pytest.approx(0.0)


def _mutate(plays: pl.DataFrame, games_to_change: list[str]) -> pl.DataFrame:
    hit = pl.col("game_id").is_in(games_to_change)
    flag = (pl.int_range(pl.len()) % 2 == 0) & hit
    return plays.with_columns(
        pl.when(hit).then(pl.col("epa") + 5.0).otherwise(pl.col("epa")).alias("epa"),
        pl.when(flag).then(1.0).otherwise(pl.col("interception")).alias("interception"),
        pl.when(flag).then(1.0).otherwise(pl.col("fumble")).alias("fumble"),
        pl.when(flag).then(1.0).otherwise(pl.col("fumble_lost")).alias("fumble_lost"),
    )


@pytest.mark.parametrize("target", ["g2", "g3"])
def test_strength_members_have_no_leakage(target):
    """Changing the plays of the target game and later ones leaves its values and all earlier
    ones unchanged; the next game does see the change (so the check is not vacuous)."""
    games = ts.games_frame()
    base = with_flags(ts.plays_frame())
    order = ["g1", "g2", "g3", "g4", "g5"]
    later = order[order.index(target) :]
    a = strength.compute(games, base)
    b = strength.compute(games, _mutate(base, later))
    for gid in order[: order.index(target) + 1]:
        for team in ("A", "B"):
            if gid == "g5" or (gid in ("g1", "g2") and team not in "AB"):
                continue
            for n in NEW_STRENGTH:
                x, y = ts.feat(a, gid, team, n), ts.feat(b, gid, team, n)
                assert (x is None and y is None) or x == pytest.approx(y, abs=1e-12), (gid, n)
    # only the one-game-later check for the members that carry the change forward
    nxt = order[order.index(target) + 1]
    if nxt == "g4":  # same season as g3: every member moves (g2 -> g3 crosses a season: priors)
        for n in NEW_STRENGTH:
            moved = [
                ts.feat(a, nxt, t, n) != pytest.approx(ts.feat(b, nxt, t, n)) for t in ("A", "B")
            ]
            assert any(moved), n


def test_strength_members_see_the_past():
    """Mutating only g2 changes the next season's week-1 prior for the rate members."""
    games = ts.games_frame()
    base = with_flags(ts.plays_frame())
    a = strength.compute(games, base)
    b = strength.compute(games, _mutate(base, ["g2"]))
    for n in ("strength.epa_off_noto", "strength.epa_def_noto", "strength.takeaway_rate"):
        assert ts.feat(a, "g3", "A", n) != pytest.approx(ts.feat(b, "g3", "A", n)), n


# one-score luck -------------------------------------------------------------------------------

T0 = datetime(2023, 9, 10, 17, 0)


def games_with(results: dict[str, float | None]) -> pl.DataFrame:
    sched = [
        ("g1", 2023, 1, 0, "A", "B"),
        ("g2", 2023, 2, 7, "B", "A"),
        ("g3", 2023, 3, 14, "A", "B"),
        ("g4", 2023, 4, 21, "B", "A"),
        ("g5", 2024, 1, 365, "A", "B"),
    ]
    return pl.DataFrame(
        {
            "game_id": [s[0] for s in sched],
            "season": [s[1] for s in sched],
            "week": [s[2] for s in sched],
            "kickoff_utc": [T0 + timedelta(days=s[3]) for s in sched],
            "home_team": [s[4] for s in sched],
            "away_team": [s[5] for s in sched],
            "result": [results.get(s[0]) for s in sched],
        },
        schema_overrides={"result": pl.Float64},
    )


def osl(results, tmp_path):
    paths = td.write_plays(tmp_path, td.make_plays(td.base_plays()))
    stats = decisions.load_game_stats(paths, 2023)
    weekly = weekly_aggregates(duckdb.connect(), paths, [2023, 2024], ["early_down"])
    return decisions.compute(games_with(results), stats, weekly)


def test_one_score_luck_values(tmp_path):
    # A's margins: g1 +3 (one-score win), g2 -10 (blowout loss; B home result +10), g3 0 (tie),
    # g4 +8 for B home so A is -8 (one-score loss). Season 2024 resets.
    res = {"g1": 3.0, "g2": 10.0, "g3": 0.0, "g4": 8.0, "g5": 1.0}
    v = osl(res, tmp_path)
    f = "decisions.one_score_luck"
    assert td.feat(v, "g1", "A", f) is None
    assert td.feat(v, "g2", "A", f) == pytest.approx((1 - 0.5) / 1)
    assert td.feat(v, "g2", "B", f) == pytest.approx((0 - 0.5) / 1)
    assert td.feat(v, "g3", "A", f) == pytest.approx((1 - 0.5) / 2)  # blowout adds a game only
    assert td.feat(v, "g4", "A", f) == pytest.approx((1 + 0.5 - 1.0) / 3)  # tie: half a win, 1 game
    assert td.feat(v, "g5", "A", f) is None


def test_one_score_luck_no_leakage(tmp_path):
    res = {"g1": 3.0, "g2": 10.0, "g3": 0.0, "g4": 8.0, "g5": 1.0}
    mut = {**res, "g3": 7.0, "g4": -1.0, "g5": 40.0}
    a, b = osl(res, tmp_path / "a"), osl(mut, tmp_path / "b")
    f = "decisions.one_score_luck"
    for gid in ("g1", "g2", "g3"):
        for t in "AB":
            x, y = td.feat(a, gid, t, f), td.feat(b, gid, t, f)
            assert (x is None and y is None) or x == pytest.approx(y), (gid, t)
    assert td.feat(a, "g4", "A", f) != pytest.approx(td.feat(b, "g4", "A", f))
