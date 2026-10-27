"""Environment builder: unit tests on a toy frame plus data checks against curated games."""

from datetime import datetime

import polars as pl

from nfl.config import get_paths
from nfl.features import environment as env
from nfl.features import store
from tests.conftest import requires_data

BUILD = datetime(2030, 1, 1)


def game(gid, season, week, home, away, sid, stadium, kick, **kw):
    base = {
        "game_id": gid,
        "season": season,
        "week": week,
        "home_team": home,
        "away_team": away,
        "stadium_id": sid,
        "stadium": stadium,
        "kickoff_utc": kick,
        "location": "Home",
        "roof": "outdoors",
        "surface": "grass",
        "home_rest": 7,
        "away_rest": 7,
        "div_game": 0,
        "weekday": "Sunday",
    }
    return {**base, **kw}


def frame(rows):
    return pl.DataFrame(rows, infer_schema_length=None).with_columns(
        pl.col("kickoff_utc").cast(pl.Datetime("us"))
    )


def val(rows, gid, feature, side):
    r = rows.filter(
        (pl.col("game_id") == gid) & (pl.col("feature") == feature) & (pl.col("side") == side)
    )
    assert r.height == 1
    return r["value"][0]


def test_haversine_det_chi():
    d = env.haversine_km(42.34, -83.0456, 41.8623, -87.6167)
    assert abs(d - 380) < 38


def test_toy_build():
    rows = frame(
        [
            # SF at DET, Sunday 1pm ET (SF is west coast)
            game(
                "A",
                2024,
                1,
                "DET",
                "SF",
                "DET00",
                "Ford Field",
                datetime(2024, 9, 8, 17),
                roof="dome",
                surface="fieldturf",
                home_rest=30,
                away_rest=7,
                div_game=0,
            ),
            # DET at SF, Thursday night: grass-blank surface, blank roof
            game(
                "B",
                2024,
                2,
                "SF",
                "DET",
                "SFO01",
                "Levi's Stadium",
                datetime(2024, 9, 13, 3),
                weekday="Thursday",
                surface="",
                roof="",
                div_game=1,
            ),
            # blank turf at Ford Field falls back to earlier fieldturf
            game(
                "C",
                2024,
                3,
                "DET",
                "GB",
                "DET00",
                "Ford Field",
                datetime(2024, 9, 22, 20),
                surface="",
                roof="",
                weekday="Sunday",
            ),
            game(
                "D",
                2024,
                4,
                "SF",
                "DET",
                "SFO01",
                "Levi's Stadium",
                datetime(2024, 9, 30, 0, 15),
                weekday="Sunday",
                location="Neutral",
            ),
        ]
    )
    out = env.build(get_paths(), rows, BUILD)
    assert set(out["source"]) == {"schedules"}
    # tz: SF (UTC-7) traveling to Detroit (UTC-4) -> +3 east; home team 0
    assert val(out, "A", "environment.tz_shift", "away") == 3
    assert val(out, "A", "environment.tz_shift", "home") == 0
    assert val(out, "B", "environment.tz_shift", "away") == -3
    assert val(out, "A", "environment.travel_km", "home") == 0
    assert 3200 < val(out, "A", "environment.travel_km", "away") < 3500
    # rest cap
    assert val(out, "A", "environment.rest_days", "home") == 14
    assert val(out, "A", "environment.rest_days", "away") == 7
    # primetime: A 1pm ET Sunday no; B Thursday yes; C 4pm ET no; D Sat 8:15pm ET yes
    assert [val(out, g, "environment.primetime", "game") for g in "ABCD"] == [0, 1, 0, 1]
    # dome: explicit, then fallback to stadium roof_type (outdoors -> 0, dome -> 1)
    assert val(out, "A", "environment.is_dome", "game") == 1
    assert val(out, "B", "environment.is_dome", "game") == 0
    assert val(out, "C", "environment.is_dome", "game") == 1
    # turf fallback
    assert val(out, "A", "environment.is_turf", "game") == 1
    assert val(out, "B", "environment.is_turf", "game") is None  # no earlier surface known
    assert val(out, "C", "environment.is_turf", "game") == 1
    assert val(out, "B", "environment.div_game", "game") == 1
    assert val(out, "D", "environment.neutral_site", "game") == 1
    assert val(out, "A", "environment.neutral_site", "game") == 0
    store.validate(out)


def test_turf_unknown_is_null():
    rows = frame(
        [
            game(
                "X",
                2024,
                1,
                "SF",
                "DET",
                "SFO01",
                "Levi's Stadium",
                datetime(2024, 9, 8, 17),
                surface="",
            )
        ]
    )
    out = env.build(get_paths(), rows, BUILD)
    assert val(out, "X", "environment.is_turf", "game") is None


def test_stadium_csv_complete_columns():
    s = pl.read_csv(env.STADIUMS_CSV)
    assert s["stadium_id"].is_unique().all()
    assert set(s["roof_type"]) <= {"dome", "retractable", "outdoors"}


@requires_data
def test_every_game_resolves_stadium_and_london():
    games = store.games_frame(get_paths())
    stadiums = env.load_stadiums()
    keys = [env.resolve_stadium(a, b) for a, b in games.select("stadium_id", "stadium").iter_rows()]
    assert all(k in stadiums for k in keys)

    london = games.filter(
        (pl.col("location") == "Neutral") & pl.col("stadium_id").str.starts_with("LON")
    ).row(0, named=True)
    out = env.build(get_paths(), games, BUILD)
    gid = london["game_id"]
    assert val(out, gid, "environment.travel_km", "home") > 5000
    assert val(out, gid, "environment.travel_km", "away") > 5000
    assert val(out, gid, "environment.neutral_site", "game") == 1
