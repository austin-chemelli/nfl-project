"""Lock: slot selection, strict as-of scoring, the public artifact, and the git guards."""

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from nfl import lock
from nfl.approaches.engine import Model, Scaler
from nfl.features import store

# Week 9 2026-style slate: Thu night, Sun London morning, Sun 1pm, Mon night (kickoffs in UTC)
GAMES = pl.DataFrame(
    {
        "game_id": ["G_THU", "G_LON", "G_SUN", "G_MON", "G_OLD"],
        "season": [2026] * 4 + [2026],
        "week": [9, 9, 9, 9, 8],
        "kickoff_utc": [
            datetime(2026, 11, 6, 1, 15),  # Thu 8:15pm ET
            datetime(2026, 11, 8, 14, 30),  # Sun 9:30am ET
            datetime(2026, 11, 8, 18, 0),  # Sun 1pm ET
            datetime(2026, 11, 10, 1, 15),  # Mon 8:15pm ET
            datetime(2026, 11, 2, 18, 0),
        ],
        "home_team": ["GB", "JAX", "BUF", "DAL", "KC"],
        "away_team": ["CAR", "PHI", "BAL", "ARI", "DEN"],
        "location": ["Home", "Neutral", "Home", "Home", "Home"],
        "result": [None, None, None, None, 7.0],
        "total_line": [47.5, 44.0, 52.5, 51.5, 42.0],
    }
)
THU_LOCK = datetime(2026, 11, 5, 14, 0)  # Thu 9am ET
SAT_LOCK = datetime(2026, 11, 7, 17, 0)  # Sat noon ET


def test_slots_split_by_eastern_weekday_and_skip_started_games():
    thu = lock.slot_games(GAMES, 2026, 9, "thu", THU_LOCK)
    assert thu["game_id"].to_list() == ["G_THU"]
    sat = lock.slot_games(GAMES, 2026, 9, "sat", SAT_LOCK)
    assert sat["game_id"].to_list() == ["G_LON", "G_SUN", "G_MON"]
    late = lock.slot_games(GAMES, 2026, 9, "sat", datetime(2026, 11, 8, 18, 30))
    assert late["game_id"].to_list() == ["G_MON"]  # Sunday games already kicked off
    with pytest.raises(ValueError):
        lock.slot_games(GAMES, 2026, 9, "fri", THU_LOCK)


def test_next_week_is_the_earliest_unplayed_game():
    assert lock.next_week(GAMES, datetime(2026, 11, 3)) == (2026, 9)


def feat_rows(game_id, feature, home, away, kao):
    return [
        (2026, 9, game_id, "home", feature, home, kao, "t", "1"),
        (2026, 9, game_id, "away", feature, away, kao, "t", "1"),
    ]


def toy_store(kao):
    rows = feat_rows("G_SUN", "strength.elo_pre", 1600.0, 1500.0, kao)
    rows += [(2026, 9, "G_SUN", "game", "market.p_home_vigfree", 0.6, kao, "odds_api", "1")]
    rows += [(2026, 9, "G_SUN", "game", "market.spread_line", 3.0, kao, "odds_api", "1")]
    rows += [(2026, 9, "G_SUN", "game", "market.total_line", 52.5, kao, "odds_api", "1")]
    return pl.DataFrame(rows, schema=store.FEATURE_SCHEMA, orient="row")


def toy_model(mid="toy.fitted"):
    sc = Scaler(["strength.elo_pre"], [0.0], [100.0])
    return Model(mid, ["strength.elo_pre"], 0.0, [0.5], sc, meta={"config_hash": "abc"})


def test_scoring_uses_only_rows_strictly_before_the_lock():
    slate = GAMES.filter(pl.col("game_id") == "G_SUN")
    known = toy_store(SAT_LOCK - timedelta(hours=1))
    same = toy_store(SAT_LOCK)  # stamped exactly at the lock: must be invisible
    models = [("toy.fitted", toy_model(), True)]
    p_known = lock.score_approaches(models, known, slate, SAT_LOCK)[0].frame["p_home"][0]
    p_same = lock.score_approaches(models, same, slate, SAT_LOCK)[0].frame["p_home"][0]
    assert p_known > 0.6  # +100 Elo -> +1 SD -> logit 0.5
    assert p_same == pytest.approx(0.5)  # no features -> league average
    ens = lock.score_approaches(models, known, slate, SAT_LOCK)
    assert [s.model_id for s in ens] == ["toy.fitted", "ensemble"]
    mk = lock.market_at(known, slate, SAT_LOCK)
    assert mk["p_home"][0] == pytest.approx(0.6) and mk["source"][0] == "odds_api"
    assert lock.market_at(same, slate, SAT_LOCK).is_empty()


def test_reference_models_walk_completed_games():
    slate = GAMES.filter(pl.col("game_id") == "G_SUN")
    mk = pl.DataFrame(
        {"game_id": ["G_SUN"], "p_home": [0.6], "spread_home": [3.0], "total": [52.5]}
    )
    refs = {s.model_id: s for s in lock.score_reference(GAMES, slate, mk)}
    assert set(refs) == {"market_baseline", "elo_v0", "home_naive"}
    assert refs["market_baseline"].frame["p_home"][0] == 0.6
    assert 0.5 < refs["elo_v0"].frame["p_home"][0] < 0.6  # equal teams + home field


def test_artifact_is_deterministic_and_hash_matches(tmp_path):
    slate = GAMES.filter(pl.col("game_id") == "G_SUN")
    known = toy_store(SAT_LOCK - timedelta(hours=1))
    res = lock.LockResult(2026, 9, "sat", SAT_LOCK, slate)
    res.market = lock.market_at(known, slate, SAT_LOCK)
    res.scored = lock.score_approaches([("toy.fitted", toy_model(), True)], known, slate, SAT_LOCK)
    art = lock.build_artifact(res, "deadbee", "20261107T160000Z", "20261107T165900Z")
    p1, d1 = lock.write_artifact(tmp_path / "a", art)
    _p2, d2 = lock.write_artifact(tmp_path / "b", json.loads(json.dumps(art)))
    assert d1 == d2 and p1.name == "week_09_sat_20261107T170000Z.json"
    import hashlib

    assert hashlib.sha256(p1.read_bytes()).hexdigest() == d1
    assert p1.with_suffix(".json.sha256").read_text().startswith(d1)
    g = art["games"][0]
    assert g["market"]["p_home_vigfree"] == 0.6 and "toy.fitted" in g["models"]
    rows = lock.prediction_rows(res, "snap", "deadbee")
    assert set(rows["model_id"]) == {"toy.fitted", "ensemble"}
    assert not rows["is_backfill"].any() and set(rows["slot"]) == {"sat"}


def git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def repo(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    r = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(r)], check=True)
    git(r, "config", "user.email", "t@example.com")
    git(r, "config", "user.name", "t")
    (r / "README.md").write_text("x\n")
    git(r, "add", "README.md")
    git(r, "commit", "-q", "-m", "init")
    git(r, "push", "-q", "origin", "HEAD:main")
    return r


def lock_file(repo: Path, name="week_09_sat_x.json") -> Path:
    d = repo / lock.PUBLIC_DIR / "2026"
    d.mkdir(parents=True, exist_ok=True)
    f = d / name
    f.write_text("{}\n")
    return f


def test_commit_lock_refuses_other_staged_files(repo):
    (repo / "other.py").write_text("x = 1\n")
    git(repo, "add", "other.py")
    with pytest.raises(RuntimeError, match="other files are staged"):
        lock.commit_lock(repo, [lock_file(repo)], "lock: 2026 W09 sat")


def test_push_guard_allows_only_lock_commits(repo):
    f = lock_file(repo)
    lock.commit_lock(repo, [f], "lock: 2026 W09 sat")
    git(repo, "fetch", "-q", "origin")
    assert lock.unpushed_non_lock_commits(repo) == []
    lock.push_locks(repo)
    assert git(repo, "rev-parse", "HEAD") == git(repo, "rev-parse", "origin/main")
    # a code commit sneaks in: the guard refuses, even with a lock commit on top
    (repo / "code.py").write_text("y = 2\n")
    git(repo, "add", "code.py")
    git(repo, "commit", "-q", "-m", "feat: code")
    lock.commit_lock(repo, [lock_file(repo, "week_09_sat_y.json")], "lock: 2026 W09 sat")
    with pytest.raises(RuntimeError, match="not pushing"):
        lock.push_locks(repo)
    # a commit named like a lock but touching other files is not a lock commit
    git(repo, "reset", "-q", "--hard", "origin/main")
    (repo / "sneaky.py").write_text("z = 3\n")
    git(repo, "add", "sneaky.py")
    git(repo, "commit", "-q", "-m", "lock: 2026 W09 sat")
    assert len(lock.unpushed_non_lock_commits(repo)) == 1
