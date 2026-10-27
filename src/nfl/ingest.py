"""Raw ingestion: download upstream nflverse parquet files unchanged into snapshot folders.

Layout: raw/nflverse/<dataset>/snapshot_ts=<ts>/<filename> + manifest.json
Idempotent: a historical season already present is skipped; the current season is re-downloaded
and only written if its content hash differs from the latest snapshot.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from nfl import __version__
from nfl.config import (
    DATASETS,
    DEFAULT_SEASONS,
    NFLVERSE_BASE,
    Paths,
    current_season,
    now_utc,
    snapshot_ts,
)

USER_AGENT = f"nfl-project/{__version__} (+https://github.com/austin-chemelli/nfl-project)"


@dataclass(frozen=True)
class Manifest:
    dataset: str
    season: int | None
    filename: str
    url: str
    sha256: str
    bytes: int
    fetched_at: str
    etag: str | None
    last_modified: str | None
    snapshot_ts: str


def _url(dataset: str, season: int | None) -> tuple[str, str]:
    tag, pattern, _ = DATASETS[dataset]
    filename = pattern.format(season=season) if season is not None else pattern
    return f"{NFLVERSE_BASE}{tag}/{filename}", filename


def list_snapshots(paths: Paths, dataset: str, filename: str) -> list[tuple[str, Path]]:
    """All (snapshot_ts, file path) pairs holding this filename, oldest first."""
    base = paths.raw_dataset(dataset)
    if not base.exists():
        return []
    out = []
    for d in sorted(base.glob("snapshot_ts=*")):
        f = d / filename
        if f.exists():
            out.append((d.name.split("=", 1)[1], f))
    return out


def latest_snapshot(paths: Paths, dataset: str, season: int | None) -> Path | None:
    _, filename = _url(dataset, season)
    snaps = list_snapshots(paths, dataset, filename)
    return snaps[-1][1] if snaps else None


def _latest_sha(paths: Paths, dataset: str, filename: str) -> str | None:
    snaps = list_snapshots(paths, dataset, filename)
    if not snaps:
        return None
    m = snaps[-1][1].with_name("manifest.json")
    if not m.exists():
        return None
    for entry in json.loads(m.read_text()):
        if entry["filename"] == filename:
            return entry["sha256"]
    return None


def fetch_one(
    client: httpx.Client,
    paths: Paths,
    dataset: str,
    season: int | None,
    ts: str,
    force: bool = False,
) -> tuple[str, Manifest | None]:
    """Download one file into the snapshot folder `ts`. Returns (status, manifest)."""
    url, filename = _url(dataset, season)
    is_current = season is None or season >= current_season()
    existing = list_snapshots(paths, dataset, filename)
    if existing and not is_current and not force:
        return "skip-historical", None

    r = client.get(url, follow_redirects=True, timeout=120)
    r.raise_for_status()
    content = r.content
    sha = hashlib.sha256(content).hexdigest()
    if existing and _latest_sha(paths, dataset, filename) == sha and not force:
        return "unchanged", None

    folder = paths.raw_dataset(dataset) / f"snapshot_ts={ts}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / filename).write_bytes(content)
    manifest = Manifest(
        dataset=dataset,
        season=season,
        filename=filename,
        url=url,
        sha256=sha,
        bytes=len(content),
        fetched_at=now_utc().isoformat(),
        etag=r.headers.get("etag"),
        last_modified=r.headers.get("last-modified"),
        snapshot_ts=ts,
    )
    mpath = folder / "manifest.json"
    entries = json.loads(mpath.read_text()) if mpath.exists() else []
    entries.append(asdict(manifest))
    mpath.write_text(json.dumps(entries, indent=2))
    return "written", manifest


def ingest(
    paths: Paths,
    datasets: list[str] | None = None,
    seasons: dict[str, tuple[int, int]] | None = None,
    force: bool = False,
) -> list[tuple[str, int | None, str]]:
    """Fetch all requested datasets into one snapshot folder per dataset. Returns per-file statuses."""
    datasets = datasets or ["schedules", *DEFAULT_SEASONS.keys()]
    seasons = {**DEFAULT_SEASONS, **(seasons or {})}
    ts = snapshot_ts()
    results: list[tuple[str, int | None, str]] = []
    with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
        for ds in datasets:
            if DATASETS[ds][2] is None:
                status, _ = fetch_one(client, paths, ds, None, ts, force)
                results.append((ds, None, status))
                continue
            lo, hi = seasons[ds]
            for season in range(lo, hi + 1):
                try:
                    status, _ = fetch_one(client, paths, ds, season, ts, force)
                except httpx.HTTPStatusError as e:
                    status = f"http-{e.response.status_code}"
                results.append((ds, season, status))
    return results
