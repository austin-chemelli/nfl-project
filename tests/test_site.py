"""Site JSON contract: statuses, structure, and the rule that previews never override locks."""

import json
from datetime import datetime

import polars as pl
import pytest

from nfl import site
from nfl.config import Paths
from nfl.predict import PRED_SCHEMA
from tests.conftest import DATA

GAMES = pl.DataFrame(
    {
        "game_id": ["A", "B"],
        "season": [2026, 2026],
        "week": [8, 8],
        "kickoff_utc": [datetime(2026, 10, 25, 17), datetime(2026, 11, 1, 18)],
    }
)


def pred(gid, mid, lock, backfill, p):
    return {"game_id": gid, "season": 2026, "week": 8, "model_id": mid, "model_version": "x",
            "lock_ts": lock, "data_snapshot_ts": "s", "p_home": p, "spread_home": 1.0, "total": 44.0,
            "sd_margin": 13.5, "is_backfill": backfill, "slot": None if backfill else "sat",
            "contributions": None}  # fmt: skip


def test_best_rows_prefers_last_lock_before_kickoff_over_backfill(tmp_path):
    paths = Paths(tmp_path)
    paths.marts.mkdir(parents=True)
    rows = [
        pred("A", "m", datetime(2026, 10, 25, 16), True, 0.50),  # backfill
        pred("A", "m", datetime(2026, 10, 24, 16), False, 0.60),  # a real lock: wins
        pred("A", "m", datetime(2026, 10, 25, 18), False, 0.70),  # after kickoff: ignored
        pred("B", "m", datetime(2026, 11, 1, 17), True, 0.40),
    ]
    pl.DataFrame(rows, schema=PRED_SCHEMA).write_parquet(paths.marts / "predictions.parquet")
    best = {
        r["game_id"]: r
        for r in site.best_rows(paths, GAMES, datetime(2026, 10, 26)).iter_rows(named=True)
    }
    assert best["A"]["status"] == site.LOCKED and best["A"]["p_home"] == 0.60
    assert best["B"]["status"] == site.BACKFILL


@pytest.mark.skipif(
    not (DATA.site / "meta.json").exists(), reason="needs marts/site (run nfl site)"
)
def _band_inputs(n_teams: int) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Two weeks of `n_teams` teams, paired off; team i's week-2 value is i."""
    known = datetime(2026, 10, 1)
    games, feats = [], []
    for week, kick in ((1, datetime(2026, 10, 2)), (2, datetime(2026, 10, 9))):
        for i in range(0, n_teams, 2):
            gid = f"{week}_{i}"
            games.append({"game_id": gid, "kickoff_utc": kick, "home_team": f"T{i}", "away_team": f"T{i + 1}"})  # fmt: skip
            for side, v in (("home", i), ("away", i + 1)):
                value = float(v) if week == 2 else -100.0  # week 1 must lose to the later game
                feats.append({"game_id": gid, "feature": "f.x", "side": side, "value": value, "known_as_of": known})  # fmt: skip
    feats.append({"game_id": "2_0", "feature": "f.game", "side": "game", "value": 1.0, "known_as_of": known})  # fmt: skip
    return pl.DataFrame(games), pl.DataFrame(feats)


def test_feature_bands_use_each_teams_latest_value_and_skip_game_features():
    games, feats = _band_inputs(32)
    bands = site.feature_bands(feats, games, datetime(2026, 10, 20))
    assert list(bands) == ["f.x"]
    assert bands["f.x"] == {"lo": 3.1, "hi": 27.9, "iqr": 15.5}  # team values 0..31


def test_feature_bands_ignore_rows_not_known_yet_and_thin_features():
    games, feats = _band_inputs(32)
    assert site.feature_bands(feats, games, datetime(2026, 9, 1)) == {}
    games, feats = _band_inputs(10)
    assert site.feature_bands(feats, games, datetime(2026, 10, 20)) == {}


def test_real_contract_shape():
    meta = json.loads((DATA.site / "meta.json").read_text())
    assert meta["schema_version"] == site.SCHEMA_VERSION
    assert {"models", "approaches", "groups", "weeks", "current_week"} <= set(meta)
    sl = json.loads(
        (DATA.site / f"slate_{meta['season']}_{meta['current_week']:02d}.json").read_text()
    )
    for g in sl["games"]:
        for m in g["models"].values():
            assert m["status"] in (site.LOCKED, site.BACKFILL, site.PREVIEW, site.PREGAME)
            assert 0 < m["p_home"] < 1
        detail = json.loads((DATA.site / "game" / f"{g['game_id']}.json").read_text())
        assert {"contributions", "features", "tendencies", "injuries", "narrative"} <= set(detail)


def test_write_retro_publishes_only_2026_and_validates(tmp_path):
    import shutil
    from pathlib import Path

    from nfl import publish
    from nfl.retro.schema import RetroGame, WeekRecap

    fix = Path(__file__).parent / "fixtures" / "retro"
    paths = Paths(tmp_path)
    for season in (2025, 2026):
        d = paths.marts / "retro" / f"season={season}"
        d.mkdir(parents=True)
        shutil.copy(fix / "game_2026_08_CAR_GB.json", d / "2026_08_CAR_GB.json")
        shutil.copy(fix / "recap_2026_08.json", d / "recap_08.json")
    (paths.marts / "retro" / "season=2026" / "bad.json").write_text("{}")
    assert site.write_retro(paths, 2025) == []
    assert not paths.site.exists()
    names = site.write_retro(paths, 2026)
    assert sorted(names) == ["recap_2026_08.json", "retro/2026_08_CAR_GB.json"]
    RetroGame.model_validate_json((paths.site / "retro" / "2026_08_CAR_GB.json").read_text())
    WeekRecap.model_validate_json((paths.site / "recap_2026_08.json").read_text())
    planned = publish.plan(paths, repo=tmp_path)
    assert any(k.endswith("/retro/2026_08_CAR_GB.json") for k in planned)
    assert any(k.endswith("/recap_2026_08.json") for k in planned)
