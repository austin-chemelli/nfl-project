"""Tiny synthetic curated tables for the SQL-model and candidate tests."""

from __future__ import annotations

import numpy as np
import polars as pl

from nfl.config import Paths

PLAY = {
    "week": 1, "season_type": "REG", "game_id": "g", "play_id": 1.0, "posteam": "A", "defteam": "B",
    "epa": 0.0, "wp": 0.5, "success": 0.0, "down": 1.0, "qtr": 1.0, "pass": 1.0, "rush": 0.0,
    "interception": 0.0, "fumble": 0.0, "fumble_lost": 0.0, "sack": 0.0, "qb_dropback": 1.0,
    "pass_oe": 0.0, "passer_player_id": "qb1",
}  # fmt: skip
GAME = {
    "game_type": "REG", "week": 1, "result": 0, "total": 40, "spread_line": 0.0,
    "total_line": 40.0, "roof": "dome", "wind": None,
}  # fmt: skip
SCHEMA_PLAYS = {
    k: (pl.String if isinstance(v, str) else pl.Float64) for k, v in PLAY.items() if k != "week"
} | {"week": pl.Int32}


def play(**kw) -> dict:
    return PLAY | kw


def write_table(paths: Paths, table: str, rows: list[dict], schema=None) -> None:
    """Write rows partitioned by their `season` (which is dropped from the file, as the hive path
    carries it)."""
    df = pl.DataFrame(rows, schema=schema, infer_schema_length=None)
    for (season,), part in df.partition_by("season", as_dict=True).items():
        d = paths.curated_table(table) / f"season={season}"
        d.mkdir(parents=True, exist_ok=True)
        part.drop("season").write_parquet(d / "data_0.parquet")


def write_plays(paths: Paths, plays: list[dict]) -> None:
    write_table(paths, "plays", plays, {**SCHEMA_PLAYS, "season": pl.Int64})


def write_games(paths: Paths, games: list[dict]) -> None:
    write_table(
        paths, "games", [GAME | g for g in games],
        {"game_id": pl.String, "game_type": pl.String, "season": pl.Int64, "week": pl.Int32,
         "home_team": pl.String, "away_team": pl.String, "result": pl.Int32, "total": pl.Int32,
         "spread_line": pl.Float64, "total_line": pl.Float64, "roof": pl.String, "wind": pl.Int32},
    )  # fmt: skip


def write_participation(paths: Paths, rows: list[dict]) -> None:
    write_table(
        paths, "participation", rows,
        {"game_id": pl.String, "play_id": pl.Float64, "was_pressure": pl.Boolean,
         "time_to_throw": pl.Float64, "season": pl.Int64},
    )  # fmt: skip


def write_predictions(paths: Paths, rows: list[dict]) -> None:
    pl.DataFrame(
        rows,
        schema={"game_id": pl.String, "model_id": pl.String, "is_backfill": pl.Boolean,
                "spread_home": pl.Float64, "total": pl.Float64},
    ).write_parquet(_mart(paths, "predictions"))  # fmt: skip


def _mart(paths: Paths, name: str):
    paths.marts.mkdir(parents=True, exist_ok=True)
    return paths.marts / f"{name}.parquet"


TEAMS = ["A", "B", "C", "D", "E", "F", "G", "H"]


def league(paths: Paths, seasons=(2020, 2021, 2022, 2023), weeks=8, seed=3, noise=3.0):
    """Eight teams with hidden skills, a fixed pairing each week, ten plays per team-game whose EPA is
    the team's skill plus noise, results driven by the skill gap, and a Student that predicts 0."""
    rng = np.random.default_rng(seed)
    plays, games, preds = [], [], []
    for season in seasons:
        skill = dict(zip(TEAMS, rng.normal(0, 0.15, len(TEAMS)), strict=True))
        for week in range(1, weeks + 1):
            order = list(rng.permutation(TEAMS))
            for i in range(0, len(order), 2):
                h, a = order[i], order[i + 1]
                gid = f"{season}_{week:02d}_{a}_{h}"
                result = round(40 * (skill[h] - skill[a]) + rng.normal(0, noise))
                games.append(
                    {"game_id": gid, "season": season, "week": week, "home_team": h,
                     "away_team": a, "result": result}
                )  # fmt: skip
                preds.append(
                    {"game_id": gid, "model_id": "student", "is_backfill": True,
                     "spread_home": 0.0, "total": 40.0}
                )  # fmt: skip
                n = 0
                for off, de in ((h, a), (a, h)):
                    for _ in range(10):
                        n += 1
                        plays.append(
                            play(season=season, week=week, game_id=gid, play_id=float(n),
                                 posteam=off, defteam=de, epa=float(skill[off] - skill[de]
                                 + rng.normal(0, 0.2)), success=float(rng.random() < 0.5))
                        )  # fmt: skip
    write_plays(paths, plays)
    write_games(paths, games)
    write_predictions(paths, preds)
    return plays, games
