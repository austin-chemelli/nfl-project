"""Paths and environment. The data root is always a filesystem path (see .notes/brainstorm.md)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

NFLVERSE_BASE = "https://github.com/nflverse/nflverse-data/releases/download/"

# dataset name -> (release tag, filename pattern, first season). None season => single file.
DATASETS: dict[str, tuple[str, str, int | None]] = {
    "schedules": ("schedules", "games.parquet", None),
    "pbp": ("pbp", "play_by_play_{season}.parquet", 1999),
    "ftn_charting": ("ftn_charting", "ftn_charting_{season}.parquet", 2022),
    "injuries": ("injuries", "injuries_{season}.parquet", 2009),
    "depth_charts": ("depth_charts", "depth_charts_{season}.parquet", 2001),
    "participation": ("pbp_participation", "pbp_participation_{season}.parquet", 2016),
    # Player-level sources (ADR 0027, M24). Optional: a failed download is logged, never fatal,
    # since nothing in a lock reads them yet.
    "player_stats": ("stats_player", "stats_player_week_{season}.parquet", 1999),
    "snap_counts": ("snap_counts", "snap_counts_{season}.parquet", 2013),  # 2012's file is empty
    "pfr_pass": ("pfr_advstats", "advstats_week_pass_{season}.parquet", 2018),
    "pfr_rush": ("pfr_advstats", "advstats_week_rush_{season}.parquet", 2018),
    "pfr_rec": ("pfr_advstats", "advstats_week_rec_{season}.parquet", 2018),
    "pfr_def": ("pfr_advstats", "advstats_week_def_{season}.parquet", 2018),
    "players": ("players", "players.parquet", None),
    "contracts": ("contracts", "historical_contracts.parquet", None),
    "draft_picks": ("draft_picks", "draft_picks.parquet", None),
}

# Datasets whose download or curate may fail without failing the job (ADR 0027).
OPTIONAL_DATASETS: frozenset[str] = frozenset(
    {"player_stats", "snap_counts", "pfr_pass", "pfr_rush", "pfr_rec", "pfr_def",
     "players", "contracts", "draft_picks"}
)  # fmt: skip
# Single-file datasets fetched on every default ingest (refetched each run; unchanged files skip).
SINGLE_FILE_DATASETS: tuple[str, ...] = ("schedules", "players", "contracts", "draft_picks")

# POC defaults. Historical seasons are fetched once; the current season is re-fetched each run.
DEFAULT_SEASONS: dict[str, tuple[int, int]] = {
    "pbp": (1999, 2026),
    "ftn_charting": (2022, 2026),
    "injuries": (2009, 2026),
    "depth_charts": (2009, 2026),
    "participation": (2016, 2025),  # published after each season; none for the current one
    "player_stats": (1999, 2026),
    "snap_counts": (2013, 2026),
    "pfr_pass": (2018, 2026),
    "pfr_rush": (2018, 2026),
    "pfr_rec": (2018, 2026),
    "pfr_def": (2018, 2026),
}

# History starts here (pbp + schedules). Fits train from FIRST_TRAIN_SEASON so Elo and the
# season-to-date priors have warmed up; scored seasons start at FIRST_SCORED_SEASON (M1.17).
FIRST_SEASON = 1999
FIRST_TRAIN_SEASON = 2002
FIRST_SCORED_SEASON = 2005


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def raw(self) -> Path:
        return self.root / "raw" / "nflverse"

    @property
    def curated(self) -> Path:
        return self.root / "curated"

    @property
    def marts(self) -> Path:
        return self.root / "marts"

    @property
    def site(self) -> Path:
        return self.marts / "site"

    def raw_dataset(self, dataset: str) -> Path:
        return self.raw / dataset

    def curated_table(self, table: str) -> Path:
        return self.curated / table


def get_paths() -> Paths:
    root = Path(os.environ.get("NFL_DATA_ROOT", "./data")).expanduser().resolve()
    return Paths(root)


def now_utc() -> datetime:
    return datetime.now(UTC)


def snapshot_ts(dt: datetime | None = None) -> str:
    """Filesystem-safe ISO timestamp used as a snapshot partition value."""
    return (dt or now_utc()).strftime("%Y%m%dT%H%M%SZ")


def current_season(dt: datetime | None = None) -> int:
    """NFL season year: seasons start in September and run into the next calendar year."""
    dt = dt or now_utc()
    return dt.year if dt.month >= 8 else dt.year - 1
