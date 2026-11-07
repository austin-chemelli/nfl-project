"""Weather features (ADR 0024, M20.10): `weather.temp_f`, `weather.wind_mph`, `weather.precip_pct`.

Game-level. Completed games: nflverse's kickoff temperature and wind for open-air games (precipitation
isn't recorded, so it stays null), stamped by the store's rule (kickoff - 2h). Upcoming games: every
Open-Meteo forecast we fetched (`nfl.weather`), each stamped at its fetch time, so a lock sees the
latest forecast before it; a fetch that landed at or after kickoff is dropped. The store only
upserts, so a played game keeps the forecast rows written while it was upcoming, beside nflverse's
values when nflverse has them (about half of 2026's open-air games so far). Games under a roof are
null. Training uses observed kickoff weather and live locks use forecasts: a mild optimism.

No approach reads this family: `environment.temp_c` and `wind_kph` are registered (planned) in the
Venue & weather group, and filling those would move every public line mid-season. These feed the
totals model and the swing list; the group gains weather in model wave 3.
"""

from __future__ import annotations

import warnings
from datetime import datetime

import polars as pl

from nfl import weather
from nfl.config import Paths
from nfl.features import store

SOURCE = "weather"
VERSION = "1"
FEATURES = ("weather.temp_f", "weather.wind_mph", "weather.precip_pct")


def history(games: pl.DataFrame) -> pl.DataFrame:
    """Played open-air games: nflverse's kickoff temperature and wind (stamped by the store)."""
    done = games.filter(
        pl.col("result").is_not_null() & pl.col("roof").is_in(list(weather.OPEN_AIR))
    )
    return pl.concat([
        done.select("game_id", pl.lit("weather.temp_f").alias("feature"), pl.col("temp").cast(pl.Float64).alias("value")),
        done.select("game_id", pl.lit("weather.wind_mph").alias("feature"), pl.col("wind").cast(pl.Float64).alias("value")),
    ]).filter(pl.col("value").is_not_null())  # fmt: skip


def forecast_rows(games: pl.DataFrame, forecasts: pl.DataFrame) -> pl.DataFrame:
    """Unplayed games: every forecast at its fetch time; a fetch at or after kickoff is dropped."""
    if forecasts.is_empty():
        return pl.DataFrame(schema={"game_id": pl.Utf8, "feature": pl.Utf8, "value": pl.Float64,
                                    "known_as_of": pl.Datetime("us")})  # fmt: skip
    kick = games.filter(pl.col("result").is_null()).select(
        "game_id",
        pl.col("kickoff_utc").dt.replace_time_zone(None).cast(pl.Datetime("us")).alias("_k"),
    )
    up = forecasts.join(kick, on="game_id").filter(pl.col("fetched_at") < pl.col("_k"))
    return pl.concat([
        up.select("game_id", pl.lit(f).alias("feature"), pl.col(f.split(".")[1]).alias("value"), pl.col("fetched_at").alias("known_as_of"))
        for f in FEATURES
    ]).filter(pl.col("value").is_not_null())  # fmt: skip


def compute(games: pl.DataFrame, forecasts: pl.DataFrame) -> pl.DataFrame:
    """(game_id, feature, value, known_as_of) long rows; known_as_of is null for played games."""
    hist = history(games).with_columns(pl.lit(None, dtype=pl.Datetime("us")).alias("known_as_of"))
    return pl.concat([hist, forecast_rows(games, forecasts)])


def build(paths: Paths, games: pl.DataFrame, build_ts: datetime) -> pl.DataFrame:
    parts = [
        store.from_game_values(
            history(games), games, source=SOURCE, version=VERSION, build_ts=build_ts
        )
    ]
    try:  # forecasts are context (ADR 0024): if they can't be read, the played games still build
        live = forecast_rows(games, weather.load_snapshots(paths))
        if not live.is_empty():
            parts.append(
                store.from_game_values(
                    live, games, source=SOURCE, version=VERSION, build_ts=build_ts
                )
            )
    except Exception as e:  # noqa: BLE001
        warnings.warn(f"weather forecasts skipped: {e!r}", stacklevel=2)
    return pl.concat(parts)
