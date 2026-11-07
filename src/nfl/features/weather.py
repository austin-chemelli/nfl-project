"""Weather features (ADR 0024, M20.10): `weather.temp_f`, `weather.wind_mph`, `weather.precip_pct`.

Game-level. Completed games: nflverse's kickoff temperature and wind for open-air games (precipitation
isn't recorded, so it stays null), stamped by the store's rule (kickoff - 2h). Upcoming games: every
Open-Meteo forecast we fetched (`nfl.weather`), each stamped at its fetch time, so a lock sees the
latest forecast before it. Games under a roof are null.

No approach reads this family: `environment.temp_c` and `wind_kph` are registered (planned) in the
Venue & weather group, and filling those would move every public line mid-season. These feed the
totals model and the swing list; the group gains weather in model wave 3.
"""

from __future__ import annotations

from datetime import datetime

import polars as pl

from nfl import weather
from nfl.config import Paths
from nfl.features import store

SOURCE = "weather"
VERSION = "1"
FEATURES = ("weather.temp_f", "weather.wind_mph", "weather.precip_pct")


def compute(games: pl.DataFrame, forecasts: pl.DataFrame) -> pl.DataFrame:
    """(game_id, feature, value, known_as_of?) long rows."""
    done = games.filter(
        pl.col("result").is_not_null() & pl.col("roof").is_in(list(weather.OPEN_AIR))
    )
    hist = pl.concat([
        done.select("game_id", pl.lit("weather.temp_f").alias("feature"), pl.col("temp").cast(pl.Float64).alias("value")),
        done.select("game_id", pl.lit("weather.wind_mph").alias("feature"), pl.col("wind").cast(pl.Float64).alias("value")),
    ]).filter(pl.col("value").is_not_null()).with_columns(pl.lit(None, dtype=pl.Datetime("us")).alias("known_as_of"))  # fmt: skip
    if forecasts.is_empty():
        return hist
    up = forecasts.filter(~pl.col("game_id").is_in(done["game_id"].to_list()))
    live = pl.concat([
        up.select("game_id", pl.lit(f).alias("feature"), pl.col(f.split(".")[1]).alias("value"), pl.col("fetched_at").alias("known_as_of"))
        for f in FEATURES
    ]).filter(pl.col("value").is_not_null())  # fmt: skip
    return pl.concat([hist, live])


def build(paths: Paths, games: pl.DataFrame, build_ts: datetime) -> pl.DataFrame:
    rows = compute(games, weather.load_snapshots(paths))
    hist = rows.filter(pl.col("known_as_of").is_null()).drop("known_as_of")
    live = rows.filter(pl.col("known_as_of").is_not_null())
    parts = [store.from_game_values(hist, games, source=SOURCE, version=VERSION, build_ts=build_ts)]
    if not live.is_empty():
        parts.append(
            store.from_game_values(live, games, source=SOURCE, version=VERSION, build_ts=build_ts)
        )
    return pl.concat(parts)
