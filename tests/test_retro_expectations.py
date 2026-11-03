"""M9.3: expectations from synthetic curated plays with planted rates and EPA gaps."""

import random

import polars as pl
import pytest

from nfl.config import Paths
from nfl.retro.expectations import build, load, write
from nfl.retro.schema import Expectations

COLS = {
    "game_id": pl.Utf8, "season": pl.Int64, "season_type": pl.Utf8, "home_team": pl.Utf8,
    "away_team": pl.Utf8, "posteam": pl.Utf8, "defteam": pl.Utf8, "down": pl.Float64,
    "ydstogo": pl.Float64, "play_type": pl.Utf8, "epa": pl.Float64, "success": pl.Float64,
    "interception": pl.Float64, "fumble": pl.Float64, "fumble_lost": pl.Float64,
    "qb_dropback": pl.Float64, "penalty": pl.Float64, "aborted_play": pl.Float64,
    "third_down_converted": pl.Float64, "third_down_failed": pl.Float64,
    "fourth_down_converted": pl.Float64, "fourth_down_failed": pl.Float64,
    "field_goal_attempt": pl.Float64, "field_goal_result": pl.Utf8, "kick_distance": pl.Float64,
    "extra_point_attempt": pl.Float64, "extra_point_result": pl.Utf8, "penalty_team": pl.Utf8,
    "penalty_yards": pl.Float64, "return_touchdown": pl.Float64, "punt_blocked": pl.Float64,
    "special_teams_play": pl.Float64,
}  # fmt: skip


def _p(**kw):
    return {c: kw.get(c) for c in COLS} | {
        "game_id": "g", "season": 2020, "season_type": "REG", "home_team": "H",
        "away_team": "A", "posteam": "H", "defteam": "A",
    } | kw  # fmt: skip


def _write(tmp_path, rows, games):
    paths = Paths(tmp_path)
    for s in {r["season"] for r in rows}:
        d = paths.curated_table("plays") / f"season={s}"
        d.mkdir(parents=True, exist_ok=True)
        df = pl.DataFrame([r for r in rows if r["season"] == s], schema=COLS)
        df.drop("season").write_parquet(d / "p.parquet")
    for s in {g["season"] for g in games}:
        d = paths.curated_table("games") / f"season={s}"
        d.mkdir(parents=True, exist_ok=True)
        pl.DataFrame([g for g in games if g["season"] == s]).drop("season").write_parquet(
            d / "g.parquet"
        )
    return paths


def _third(ydstogo, conv, epa, **kw):
    return _p(down=3.0, ydstogo=ydstogo, play_type="pass", epa=epa,
              third_down_converted=float(conv), third_down_failed=float(not conv), **kw)  # fmt: skip


def _synthetic(tmp_path):
    rows = []
    for i in range(100):
        rows.append(_third(1.0, i < 70, 1.0 if i < 70 else -1.0))  # 70%, gap 2.0
        rows.append(_third(12.0, i < 20, 1.5 if i < 20 else -0.5))  # 20%, gap 2.0
    for i in range(100):
        made = i < 80
        rows.append(_p(field_goal_attempt=1.0, kick_distance=42.0,
                       field_goal_result="made" if made else "missed",
                       epa=0.5 if made else -2.0))  # fmt: skip
    for i in range(10):
        lost = i < 5
        rows.append(
            _p(fumble=1.0, fumble_lost=float(lost), play_type="pass", epa=-2.0 if lost else -0.5)
        )
    for i in range(10):
        rows.append(_p(extra_point_attempt=1.0, extra_point_result="good" if i < 9 else "failed"))
    for i in range(20):
        rows.append(_p(qb_dropback=1.0, play_type="pass", interception=0.0, epa=0.2))
    rows.append(_p(qb_dropback=1.0, play_type="pass", interception=1.0, epa=-4.8))
    # penalties: 10 yards each, offense penalized (epa -1) and defense penalized (epa +1)
    rows.append(
        _p(penalty=1.0, play_type="no_play", penalty_team="H", penalty_yards=10.0, epa=-1.0)
    )
    rows.append(_p(penalty=1.0, play_type="no_play", penalty_team="A", penalty_yards=10.0, epa=1.0))
    rows.append(_p(return_touchdown=1.0, special_teams_play=1.0, epa=6.0))
    # a pick-six is a turnover, not a special-teams big play
    rows.append(_p(return_touchdown=1.0, special_teams_play=0.0, play_type="pass", epa=-7.0))
    rows.append(
        _p(field_goal_attempt=1.0, kick_distance=45.0, field_goal_result="blocked", epa=-4.0)
    )
    # excluded: kneel / spike / no_play on 3rd down, postseason
    rows.append(_p(down=3.0, ydstogo=1.0, play_type="qb_kneel", epa=0.0, third_down_converted=1.0,
                   third_down_failed=0.0))  # fmt: skip
    rows.append(_p(down=3.0, ydstogo=1.0, play_type="qb_spike", epa=0.0, third_down_converted=0.0,
                   third_down_failed=1.0))  # fmt: skip
    rows.append(_p(down=3.0, ydstogo=1.0, play_type="no_play", epa=0.0, third_down_converted=0.0,
                   third_down_failed=1.0))  # fmt: skip
    for _ in range(50):
        rows.append(_third(1.0, False, -1.0, season_type="POST"))
    # v2 exclusions: a 3rd-down turnover, an aborted play and a blocked FG must not count
    rows.append(_third(1.0, False, -5.0, interception=1.0))
    rows.append(_third(1.0, False, -5.0, fumble_lost=1.0))
    rows.append(_third(1.0, False, -5.0, aborted_play=1.0))
    rows.append(
        _p(field_goal_attempt=1.0, kick_distance=42.0, field_goal_result="blocked", epa=-5.0)
    )
    # played-like: efficient team wins more
    rng = random.Random(1)
    games = []
    for k in range(300):
        gid = f"G{k}"
        home_better = rng.random() < 0.5
        eff = rng.random() < 0.85  # better team wins 85%
        home_win = home_better if eff else not home_better
        games.append({"game_id": gid, "season": 2020, "game_type": "REG",
                      "home_score": 24 if home_win else 17, "away_score": 17 if home_win else 24})  # fmt: skip
        for team, better in (("H", home_better), ("A", not home_better)):
            for _ in range(12):
                good = rng.random() < (0.6 if better else 0.4)
                rows.append(_p(game_id=gid, posteam=team, defteam="A" if team == "H" else "H",
                               play_type="run", epa=(0.3 if good else -0.3) + rng.gauss(0, 0.1),
                               success=float(good), interception=0.0, fumble_lost=0.0))  # fmt: skip
    return _write(tmp_path, rows, games)


@pytest.fixture
def exp(tmp_path) -> Expectations:
    return build(_synthetic(tmp_path), (2020, 2020))


def test_planted_rates_and_values(exp):
    t = {b.key: b for b in exp.third_down}
    assert t["1"].rate == pytest.approx(0.70) and t["1"].n == 100  # kneel/spike/no_play/POST out
    assert t["11+"].rate == pytest.approx(0.20) and t["11+"].hi is None
    assert t["1"].value == pytest.approx(2.0) and t["11+"].value == pytest.approx(2.0)
    assert t["2-3"].n == 0
    fg = {b.key: b for b in exp.field_goal}
    assert t["1"].n == 100  # the interception, lost fumble and aborted play are out
    assert fg["40-44"].rate == pytest.approx(0.80) and fg["40-44"].n == 100  # blocked FG is out
    assert fg["40-44"].value == pytest.approx(2.5)
    assert exp.extra_point_rate == pytest.approx(0.9) and exp.extra_point_n == 10
    assert exp.fumble_lost_share == pytest.approx(0.5) and exp.fumble_n == 10
    assert exp.value_fumble_lost == pytest.approx(1.5)


def test_interception_penalty_values(exp):
    assert exp.value_interception == pytest.approx(5.0, abs=0.05)  # 0.2 vs -4.8 (+ other dropbacks)
    assert exp.value_penalty_yard == pytest.approx(0.1)  # (1 + 1) / 20


def test_played_like_positive(exp):
    pl_ = exp.played_like
    assert pl_.n == 300
    assert pl_.b_epa > 0


def test_special_teams(exp):
    assert exp.value_special_teams_big_play == pytest.approx(5.0)
    assert exp.special_teams_big_plays_pg == pytest.approx(3 / (2 * 301))


def test_roundtrip(tmp_path, exp):
    paths = Paths(tmp_path)
    out = write(paths, exp)
    assert out == tmp_path / "marts" / "retro" / "expectations.json"
    assert load(paths) == exp and exp.version == "retro_exp_v2"
