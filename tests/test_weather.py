import json
from datetime import datetime

import httpx
import polars as pl

from nfl import weather
from nfl.config import Paths
from nfl.features import weather as wfeat

KICK = datetime(2026, 11, 8, 18, 0)


def _hourly(temp=28.0, rain=60.0, wind=17.0, gusts=30.0):
    times = [f"2026-11-08T{h:02d}:00" for h in range(24)]
    return {"time": times, "temperature_2m": [temp] * 24, "precipitation_probability": [rain] * 24,
            "wind_speed_10m": [wind] * 24, "wind_gusts_10m": [gusts] * 24}  # fmt: skip


def _games():
    return pl.DataFrame({
        "game_id": ["2026_10_BUF_KC", "2026_10_DAL_ATL", "2026_09_GB_CHI", "2026_10_SEA_LA"],
        "season": [2026] * 4,
        "kickoff_utc": [KICK, KICK, datetime(2026, 11, 1, 18), KICK],
        "stadium_id": ["KAN00", "ATL97", "CHI98", "LAX01"],
        "stadium": ["Arrowhead", "Mercedes-Benz", "Soldier Field", "SoFi"],
        "roof": ["outdoors", "closed", "outdoors", None],
        "result": [None, None, 7, None],
        "temp": [None, None, 41, None],
        "wind": [None, None, 12, None],
    }).with_columns(pl.col("kickoff_utc").dt.replace_time_zone("UTC"))  # fmt: skip


def test_open_air_trusts_the_schedule_then_the_stadium():
    assert weather.open_air("outdoors", "dome")
    assert weather.open_air("open", "retractable")
    assert not weather.open_air("closed", "outdoors")
    assert weather.open_air(None, "outdoors")
    assert not weather.open_air(None, "retractable")


def test_hour_picks_kickoff_and_skips_missing():
    h = weather._hour(_hourly(), KICK)
    assert h == {"temp_f": 28.0, "precip_pct": 60.0, "wind_mph": 17.0, "gusts_mph": 30.0}
    assert weather._hour(_hourly(), datetime(2026, 11, 9, 18)) is None
    assert weather._hour(_hourly(temp=None), KICK) is None


def test_snapshot_fetches_only_upcoming_open_air_games(tmp_path):
    asked = []

    def handler(req):
        asked.append(req.url.params["latitude"])
        return httpx.Response(200, json={"hourly": _hourly()})

    paths = Paths(root=tmp_path)
    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        n = weather.snapshot(paths, _games(), now=datetime(2026, 11, 5, 12), client=c)
    assert n == 1 and len(asked) == 1  # KC only: ATL closed, CHI played, SoFi has a roof
    [snap] = (tmp_path / "raw" / "open_meteo").glob("snapshot_ts=*/forecasts.json")
    assert json.loads(snap.read_text())[0]["game_id"] == "2026_10_BUF_KC"
    df = weather.load_snapshots(paths)
    assert df["wind_mph"].to_list() == [17.0]


def test_a_failed_fetch_writes_nothing(tmp_path):
    paths = Paths(root=tmp_path)
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))) as c:
        assert weather.snapshot(paths, _games(), now=datetime(2026, 11, 5, 12), client=c) == 0
    assert weather.load_snapshots(paths).is_empty()


def test_features_use_recorded_weather_for_played_games_and_forecasts_for_upcoming():
    fc = pl.DataFrame({
        "game_id": ["2026_10_BUF_KC", "2026_10_BUF_KC", "2026_09_GB_CHI"],
        "fetched_at": [datetime(2026, 11, 5, 12), datetime(2026, 11, 7, 12), datetime(2026, 10, 30)],
        "temp_f": [35.0, 28.0, 50.0], "wind_mph": [10.0, 17.0, 5.0],
        "gusts_mph": [None, None, None], "precip_pct": [20.0, None, 0.0],
    })  # fmt: skip
    rows = wfeat.compute(_games(), fc)
    chi = rows.filter(pl.col("game_id") == "2026_09_GB_CHI")
    assert sorted(chi["value"].to_list()) == [
        12.0,
        41.0,
    ]  # the recorded weather wins once it's played
    assert chi["known_as_of"].is_null().all()
    kc = rows.filter(
        (pl.col("game_id") == "2026_10_BUF_KC") & (pl.col("feature") == "weather.wind_mph")
    )
    assert kc.sort("known_as_of")["value"].to_list() == [
        10.0,
        17.0,
    ]  # each forecast at its fetch time
    assert (
        rows.filter(pl.col("feature") == "weather.precip_pct").height == 1
    )  # a null chance is dropped
