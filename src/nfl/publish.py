"""Publish the site data to the public bucket (docs/hosting.md: site data lives in storage, not
in the site). Uploads marts/site/*.json and public/predictions/** with a 5-minute cache so the
React site sees locks and grades within minutes. Idempotent: unchanged files (by md5) are skipped.
Site JSON is stored gzipped (`Content-Encoding: gzip`; GCS decompresses for clients that don't
accept it): the build-your-own matrix is 1.3 MB raw, 270 KB gzipped. Lock artifacts stay raw so
their bytes match the committed .sha256.

Auth is application-default credentials: the job's service account in Cloud Run, Austin's gcloud
login on the laptop. Local runs never need this; the laptop publishes only when asked.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from nfl.config import Paths

CACHE_CONTROL = "public, max-age=300"
SITE_PREFIX = "site"
PREDICTIONS_PREFIX = "predictions"


@dataclass
class PublishResult:
    uploaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def plan(paths: Paths, repo: Path | None = None) -> dict[str, Path]:
    """Object name -> local file for everything that should be public."""
    out: dict[str, Path] = {}
    for f in sorted(paths.site.glob("*.json")):
        out[f"{SITE_PREFIX}/{f.name}"] = f
    pred = (repo or Path.cwd()) / "public" / "predictions"
    if pred.is_dir():
        for f in sorted(pred.rglob("*")):
            if f.is_file():
                out[f"{PREDICTIONS_PREFIX}/{f.relative_to(pred).as_posix()}"] = f
    return out


def _md5_b64(data: bytes) -> str:
    return base64.b64encode(hashlib.md5(data).digest()).decode()


def _payload(name: str, path: Path) -> tuple[bytes, str | None]:
    """Bytes to store and their Content-Encoding. mtime=0 keeps the gzip (and its md5) stable."""
    raw = path.read_bytes()
    if name.startswith(f"{SITE_PREFIX}/"):
        return gzip.compress(raw, compresslevel=9, mtime=0), "gzip"
    return raw, None


def _content_type(path: Path) -> str:
    return {".json": "application/json", ".sha256": "text/plain"}.get(
        path.suffix, "application/octet-stream"
    )


def publish(
    paths: Paths, bucket_name: str | None = None, repo: Path | None = None, client=None
) -> PublishResult:
    """Upload the plan to `bucket_name` (default env NFL_SITE_BUCKET). `client` is injectable for
    tests; it only needs `.bucket(name).blob(name)` with `.exists()`, `.md5_hash`, `.reload()`,
    `.upload_from_string()`, `.cache_control`, `.content_type`, `.content_encoding`."""
    bucket_name = bucket_name or os.environ.get("NFL_SITE_BUCKET")
    if not bucket_name:
        raise RuntimeError("no bucket: pass --bucket or set NFL_SITE_BUCKET")
    if client is None:
        from google.cloud import storage

        client = storage.Client()
    bucket = client.bucket(bucket_name)
    res = PublishResult()
    for name, path in plan(paths, repo).items():
        blob = bucket.blob(name)
        data, encoding = _payload(name, path)
        if blob.exists():
            blob.reload()
            if (
                blob.md5_hash == _md5_b64(data)
                and blob.cache_control == CACHE_CONTROL
                and blob.content_encoding == encoding
            ):
                res.skipped.append(name)
                continue
        blob.cache_control = CACHE_CONTROL
        blob.content_type = _content_type(path)
        blob.content_encoding = encoding
        blob.upload_from_string(data, content_type=_content_type(path))
        res.uploaded.append(name)
    return res
