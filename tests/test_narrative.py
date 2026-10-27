"""Narrative contract: validation rules, store round trip, feature rows with explicit stamps."""

import json
from datetime import datetime

import polars as pl
import pytest

from nfl.config import Paths
from nfl.features import narrative as feat
from nfl.llm import narrative as nar

GAMES = pl.DataFrame(
    {
        "game_id": ["2026_08_BAL_BUF"],
        "season": [2026],
        "week": [8],
        "home_team": ["BUF"],
        "away_team": ["BAL"],
        "kickoff_utc": [datetime(2026, 11, 1, 18, 0)],
    }
)


def rec(**over):
    d = nar.example()
    d.update(over)
    return nar.GameNarrative.model_validate(d)


def test_example_is_valid_and_naive_utc():
    r = rec()
    assert r.known_as_of == datetime(2026, 10, 28, 20, 0)
    assert r.kickoff_utc.tzinfo is None


def test_rejects_research_after_kickoff_and_late_or_stale_claims():
    with pytest.raises(ValueError, match="before kickoff"):
        rec(known_as_of="2026-11-01T18:00:00Z")
    d = nar.example()
    d["claims"][0]["published_at"] = "2026-10-29"
    with pytest.raises(ValueError, match="after known_as_of"):
        nar.GameNarrative.model_validate(d)
    d["claims"][0]["published_at"] = "2026-10-01"
    with pytest.raises(ValueError, match="older than"):
        nar.GameNarrative.model_validate(d)


def test_rejects_team_mismatch_and_ranges():
    d = nar.example()
    d["home"]["team"] = "MIA"
    with pytest.raises(ValueError, match="must match"):
        nar.GameNarrative.model_validate(d)
    d = nar.example()
    d["home"]["sentiment"] = 1.5
    with pytest.raises(ValueError):
        nar.GameNarrative.model_validate(d)


def test_ingest_stores_by_game_and_timestamp(tmp_path):
    paths = Paths(tmp_path)
    src = tmp_path / "r.json"
    src.write_text(json.dumps(nar.example()))
    out = nar.ingest(paths, src)
    assert out.name == "2026_08_BAL_BUF_20261028T200000Z.json"
    assert len(nar.load_records(paths)) == 1
    assert nar.load_records(paths, (2025, 2025)) == []


def test_feature_rows_carry_the_record_stamp():
    rows = feat.rows_from_records([rec()], GAMES)
    assert set(rows["known_as_of"]) == {datetime(2026, 10, 28, 20, 0)}
    assert set(rows["version"]) == {nar.PROMPT_VERSION}
    assert set(rows["source"]) == {feat.SOURCE}
    team = rows.filter(pl.col("side") != "game")
    assert team.height == 2 * len(feat.TEAM_FIELDS)
    game = rows.filter(pl.col("side") == "game")
    assert set(game["feature"]) == {f"narrative.{f}" for f in feat.GAME_FIELDS}
    v = dict(
        zip(
            team.filter(pl.col("side") == "away")["feature"],
            team.filter(pl.col("side") == "away")["value"],
        )
    )
    assert v["narrative.revenge"] == 1.0 and v["narrative.injury_impact"] == 2.0


def test_two_runs_for_one_game_both_stored_and_as_of_picks_latest():
    from nfl.features import store

    a = rec()
    b = rec(known_as_of="2026-10-30T12:00:00Z")
    b.home.sentiment = -0.9
    rows = feat.rows_from_records([a, b], GAMES)
    sent = rows.filter((pl.col("feature") == "narrative.sentiment") & (pl.col("side") == "home"))
    assert sent.height == 2
    latest = store.as_of(sent, datetime(2026, 10, 31, 12, 0))
    assert latest["value"][0] == pytest.approx(-0.9)
    earlier = store.as_of(sent, datetime(2026, 10, 29, 12, 0))
    assert earlier["value"][0] == pytest.approx(0.3)
