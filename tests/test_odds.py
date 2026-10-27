"""Odds API: parsing (real trimmed fixture), game matching, consensus, curated lines, live market
features, the credit guard, and key redaction. No network."""

import json
from datetime import datetime
from pathlib import Path

import httpx
import polars as pl
import pytest

from nfl import odds
from nfl.config import Paths
from nfl.features import market

FIXTURE = Path(__file__).parent / "fixtures" / "odds_live.json"
SNAP = datetime(2026, 10, 26, 22, 0)
GAMES = pl.DataFrame(
    {
        "game_id": ["2026_08_BAL_BUF", "2026_08_KC_DEN", "2025_08_BAL_BUF"],
        "season": [2026, 2026, 2025],
        "week": [8, 8, 8],
        "home_team": ["BUF", "DEN", "BUF"],
        "away_team": ["BAL", "KC", "BAL"],
        "kickoff_utc": [
            datetime(2026, 11, 1, 18, 0),
            datetime(2026, 11, 1, 21, 25),
            datetime(2025, 10, 26, 17, 0),
        ],
        "spread_line": [3.0, -1.0, 2.0],
        "total_line": [52.5, 42.5, 47.0],
        "home_moneyline": [-180, 105, -130],
        "away_moneyline": [150, -125, 110],
    }
)


def write_snapshot(root: Path, ts: datetime, events: list) -> None:
    s = ts.strftime("%Y%m%dT%H%M%SZ")
    d = root / "raw" / "odds_api" / "live" / f"snapshot_ts={s}"
    d.mkdir(parents=True)
    (d / "odds.json").write_text(json.dumps(events))
    (d / "manifest.json").write_text(
        json.dumps(
            {"kind": "live", "snapshot_ts": s, "fetched_at": ts.isoformat(), "requests_used": 3}
        )
    )


def events():
    return json.loads(FIXTURE.read_text())


def test_parse_real_fixture_sides_and_points():
    df = odds.parse_events(events(), SNAP)
    assert set(df["market"]) == {"h2h", "spreads", "totals"}
    assert set(df["side"]) == {"home", "away", "over", "under"}
    assert set(df["home_team"]) == {"BUF", "DEN"}
    buf = df.filter((pl.col("home_team") == "BUF") & (pl.col("market") == "spreads"))
    home_pts = buf.filter(pl.col("side") == "home")["point"]
    assert (home_pts < 0).all()  # Buffalo favored at home: book quotes home −3.5


def test_unknown_team_fails_loudly():
    ev = events()[:1]
    ev[0]["home_team"] = "Springfield Atoms"
    with pytest.raises(ValueError, match="unknown team"):
        odds.parse_events(ev, SNAP)


def test_match_games_picks_nearest_kickoff_only():
    m = odds.match_games(odds.parse_events(events(), SNAP), GAMES)
    assert set(m["game_id"]) == {"2026_08_BAL_BUF", "2026_08_KC_DEN"}  # not last year's BAL@BUF


def test_curate_consensus_and_closing_flag(tmp_path):
    paths = Paths(tmp_path)
    write_snapshot(tmp_path, SNAP, events())
    later = datetime(2026, 11, 1, 17, 50)  # 10 min before BUF kickoff
    write_snapshot(tmp_path, later, events())
    assert odds.curate_lines(paths, GAMES) > 0
    lines = odds.read_lines(paths)
    closing = lines.filter(pl.col("is_closing")).select("game_id", "snapshot_ts").unique()
    assert closing.filter(pl.col("game_id") == "2026_08_BAL_BUF")["snapshot_ts"][0] == later
    c = odds.consensus(lines).filter(pl.col("game_id") == "2026_08_BAL_BUF")
    assert (c["spread_home"] > 0).all()  # nflverse sign: + = home favored
    assert ((c["p_home_vigfree"] > 0.5) & (c["p_home_vigfree"] < 1)).all()
    assert c["home_spread_price"].is_not_null().all()


def test_live_market_features_use_snapshot_time_and_ignore_post_kickoff(tmp_path):
    paths = Paths(tmp_path)
    write_snapshot(tmp_path, SNAP, events())
    write_snapshot(tmp_path, datetime(2026, 11, 1, 22, 0), events())  # after both kickoffs
    odds.curate_lines(paths, GAMES)
    rows = market.build(paths, GAMES, datetime(2026, 10, 27, 12, 0))
    live = rows.filter(pl.col("source") == "odds_api")
    assert set(live["known_as_of"]) == {SNAP}
    assert set(live["feature"]) >= {"market.p_home_vigfree", "market.line_move_pts"}
    # upcoming games with odds don't also get schedule rows; last year's game does
    sched = rows.filter(pl.col("source") == "schedules")
    assert set(sched["game_id"]) == {"2025_08_BAL_BUF"}


def test_guard_respects_soft_cap(tmp_path):
    paths = Paths(tmp_path)
    write_snapshot(tmp_path, SNAP, [])
    mf = next(tmp_path.glob("raw/odds_api/live/*/manifest.json"))
    mf.write_text(
        json.dumps({"fetched_at": SNAP.isoformat(), "requests_used": odds.MONTHLY_SOFT_CAP - 2})
    )
    with pytest.raises(odds.CreditCapError):
        odds.guard(paths, 3)


def test_errors_never_contain_the_key(monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", "SECRET123")

    def handler(request):
        return httpx.Response(401, json={"message": "nope"})

    real_client = httpx.Client
    monkeypatch.setattr(
        odds.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)
    )
    with pytest.raises(odds.OddsAPIError) as e:
        odds._get("/sports/x/odds", {"regions": "us"})
    assert "SECRET123" not in str(e.value)
    assert e.value.__cause__ is None and e.value.__suppress_context__
