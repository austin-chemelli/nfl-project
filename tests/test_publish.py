"""nfl publish: what goes public, with what headers, and that unchanged files are skipped."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
from pathlib import Path

from nfl.config import Paths
from nfl.publish import CACHE_CONTROL, plan, publish


class _Blob:
    def __init__(self, store: dict, name: str):
        self.store, self.name = store, name
        self.cache_control = None
        self.content_type = None
        self.content_encoding = None

    def exists(self):
        return self.name in self.store

    def reload(self):
        rec = self.store[self.name]
        self.md5_hash, self.cache_control = rec["md5"], rec["cache_control"]
        self.content_encoding = rec["content_encoding"]

    def upload_from_string(self, data, content_type=None):
        self.store[self.name] = {
            "md5": base64.b64encode(hashlib.md5(data).digest()).decode(),
            "cache_control": self.cache_control,
            "content_type": content_type,
            "content_encoding": self.content_encoding,
            "data": data,
        }


class _Bucket:
    def __init__(self, store):
        self.store = store

    def blob(self, name):
        return _Blob(self.store, name)


class _Client:
    def __init__(self):
        self.store: dict = {}

    def bucket(self, name):
        return _Bucket(self.store)


def _layout(tmp_path: Path) -> tuple[Paths, Path]:
    paths = Paths(tmp_path / "data")
    paths.site.mkdir(parents=True)
    (paths.site / "meta.json").write_text(json.dumps({"schema_version": "2"}))
    (paths.site / "scorecard.json").write_text("{}")
    (paths.marts / "other.parquet").write_bytes(b"not public")
    repo = tmp_path / "repo"
    pred = repo / "public" / "predictions" / "2026"
    pred.mkdir(parents=True)
    (pred / "week_09_thu_x.json").write_text("{}")
    (pred / "week_09_thu_x.json.sha256").write_text("abc  week_09_thu_x.json\n")
    return paths, repo


def test_plan_lists_site_json_and_lock_files_only(tmp_path):
    paths, repo = _layout(tmp_path)
    names = sorted(plan(paths, repo))
    assert names == [
        "predictions/2026/week_09_thu_x.json",
        "predictions/2026/week_09_thu_x.json.sha256",
        "site/meta.json",
        "site/scorecard.json",
    ]


def test_publish_uploads_with_cache_header_then_skips_unchanged(tmp_path):
    paths, repo = _layout(tmp_path)
    client = _Client()
    first = publish(paths, "bucket", repo, client=client)
    assert len(first.uploaded) == 4 and not first.skipped
    rec = client.store["site/meta.json"]
    assert rec["cache_control"] == CACHE_CONTROL
    assert rec["content_type"] == "application/json"
    # site JSON is stored gzipped; lock artifacts stay byte-identical to the committed files
    assert rec["content_encoding"] == "gzip"
    assert json.loads(gzip.decompress(rec["data"])) == {"schema_version": "2"}
    lock = client.store["predictions/2026/week_09_thu_x.json"]
    assert lock["content_encoding"] is None and lock["data"] == b"{}"
    assert (
        client.store["predictions/2026/week_09_thu_x.json.sha256"]["content_type"] == "text/plain"
    )

    second = publish(paths, "bucket", repo, client=client)
    assert not second.uploaded and len(second.skipped) == 4

    (paths.site / "meta.json").write_text(json.dumps({"schema_version": "2", "x": 1}))
    third = publish(paths, "bucket", repo, client=client)
    assert third.uploaded == ["site/meta.json"]


def test_publish_requires_a_bucket(tmp_path, monkeypatch):
    paths, repo = _layout(tmp_path)
    monkeypatch.delenv("NFL_SITE_BUCKET", raising=False)
    try:
        publish(paths, None, repo, client=_Client())
    except RuntimeError as e:
        assert "bucket" in str(e)
    else:
        raise AssertionError("expected RuntimeError")
